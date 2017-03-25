import os
import sys
import time
import yaml
import logging
import logging.handlers
import queue
import datetime
import re
from fatsecret import Fatsecret
from PyQt5.QtCore import (QObject, QThread, pyqtSlot, pyqtSignal, Qt)
from PyQt5.QtWidgets import (QWidget, QLabel, QMessageBox, QListWidget,
                             QPushButton, QApplication, QTableWidget,
                             QGridLayout, QListWidgetItem, QTableWidgetItem,
                             QLineEdit)
from PyQt5.QtGui import (QIcon, QIntValidator)


class PiFoodScale(QWidget):
    config = {}
    fatsecret = None

    def __init__(self, config):
        self.config = config
        super().__init__()
        self.initUI()
        self.initWorkers()

    def initWorkers(self):

        self.currentFood = None
        self.currentServingAmount = None
        self.currentServingName = None
        self.currentServingId = None
        self.currentFoodEntry = None

        self.scaleThread = QThread()
        self.scaleReader = ReadScale(self.config)
        self.scaleReader.data[str].connect(self.onData)
        self.scaleReader.moveToThread(self.scaleThread)
        self.scaleThread.started.connect(self.scaleReader.run)
        self.scaleThread.start()

        self.connected = False
        self.fsThread = QThread()
        self.fatsecret = FatSecretApi(self.config)
        self.fatsecret.onLogin[dict].connect(self.onLogin)
        self.fatsecret.onEaten[dict].connect(self.onEaten)
        self.fatsecret.onEntries[dict].connect(self.onEntries)
        self.fatsecret.onFoodEntryCreate[dict].connect(self.onFoodEntryCreate)
        self.fatsecret.onFoodEntryDelete[dict].connect(self.onFoodEntryDelete)
        self.fatsecret.moveToThread(self.fsThread)
        self.fsThread.started.connect(self.fatsecret.run)
        self.fsThread.start()
        self.fatsecret.q.put({'func': 'login'})

        self.txtAmount.textChanged.connect(self.onAmountChanged)

    def initUI(self):
        self.setStyleSheet('font-size: 12px')

        btnQuit = QPushButton('Quit', self)
        btnQuit.clicked.connect(self.close)

        self.btnAdd = QPushButton("Add", self)
        self.btnAdd.setEnabled(False)
        self.btnAdd.clicked.connect(self.doAdd)
        self.btnDel = QPushButton("Del", self)
        self.btnDel.setEnabled(False)
        self.btnDel.clicked.connect(self.doDel)
        self.btnRefresh = QPushButton("Refresh", self)
        self.btnRefresh.clicked.connect(self.doRefresh)
        self.btnYesterday = QPushButton("Yesterday", self)
        self.btnYesterday.clicked.connect(self.doYesterday)

        self.lblScale = QLabel('Scale', self)
        self.lblScale.setStyleSheet('border: 1px solid black')

        self.listEaten = QListWidget()
        self.listEaten.setMinimumWidth(600)
        self.listEaten.setMaximumHeight(200)
        self.listEaten.setStyleSheet("font-size: 10px;")
        self.listEaten.itemClicked.connect(self.eatenClick)

        self.tableToday = QTableWidget()
        self.tableToday.setStyleSheet("font-size: 12px;")
        self.tableToday.setColumnCount(6)
        self.tableToday.setHorizontalHeaderLabels(
            ['Item', 'Qty', 'Cal', 'Protein', 'Fat', 'Carbs'])
        vh = self.tableToday.verticalHeader()
        vh.setDefaultSectionSize(16)
        vh.setVisible(False)
        hh = self.tableToday.horizontalHeader()
        hh.setSectionResizeMode(1)
        hh.setSectionResizeMode(0, 3)
        self.tableToday.setHorizontalHeaderLabels(
            ['Item', 'Qty', 'Cal', 'Protein', 'Fat', 'Carbs'])
        self.tableToday.setMinimumWidth(600)
        self.tableToday.itemClicked.connect(self.todayClick)

        self.txtAmount = QLineEdit('', self)
        self.txtAmount.setStyleSheet('border: 1px solid black')
        self.txtAmount.setMaximumWidth(100)
        self.txtAmount.setValidator(QIntValidator(1, 9999, self.txtAmount))
        self.lblName = QLabel('', self)
        self.lblServing = QLabel('', self)
        self.lblServingAmount = QLabel('', self)
        self.lblCalories = QLabel('', self)
        self.lblProtein = QLabel('', self)
        self.lblFat = QLabel('', self)
        self.lblCarbs = QLabel('', self)

        self.lblTCalories = QLabel('', self)
        self.lblTProtein = QLabel('', self)
        self.lblTFat = QLabel('', self)
        self.lblTCarbs = QLabel('', self)

        grid = QGridLayout()
        grid.setSpacing(1)
        # line 1 is the scale
        #   row, col, rowspan, colspan
        grid.addWidget(self.lblScale, 1, 1, 1, 5)

        grid.addWidget(self.txtAmount,           2, 1, 1, 1)
        grid.addWidget(self.lblName,             2, 2, 1, 2)

        grid.addWidget(self.lblServingAmount,    2, 4, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblServing,          2, 5, 1, 1, Qt.AlignCenter)

        grid.addWidget(QLabel('Calories', self), 4, 2, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Protein', self),  4, 3, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Fat', self),      4, 4, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Carbs', self),    4, 5, 1, 1, Qt.AlignCenter)

        grid.addWidget(QLabel('This', self),     5, 1, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblCalories,         5, 2, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblProtein,          5, 3, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblFat,              5, 4, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblCarbs,            5, 5, 1, 1, Qt.AlignCenter)

        grid.addWidget(QLabel('Today', self),    6, 1, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblTCalories,        6, 2, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblTProtein,         6, 3, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblTFat,             6, 4, 1, 1, Qt.AlignCenter)
        grid.addWidget(self.lblTCarbs,           6, 5, 1, 1, Qt.AlignCenter)

        grid.addWidget(self.tableToday,         7, 1, 1, 5)
        grid.addWidget(self.listEaten,          8, 1, 1, 5)
        grid.addWidget(self.btnAdd,             9, 1, 1, 1)
        grid.addWidget(self.btnDel,             9, 2, 1, 1)
        grid.addWidget(self.btnRefresh,         9, 3, 1, 1)
        grid.addWidget(self.btnYesterday,       9, 4, 1, 1)
        grid.addWidget(btnQuit,                 9, 5)

        self.setLayout(grid)

        self.setWindowTitle('PiFoodScale')
        self.setWindowIcon(QIcon('icon.jpg'))

        self.show()
        # self.showFullScreen()

    def checkError(self, result):
        if 'error' in result:
            QMessageBox.critical(None, "Fatsecret exception",
                                 result['error'], QMessageBox.Ok)
            return True

    def doAdd(self):
        self.fatsecret.q.put({'func': 'food_entry_create',
                              'food_id': self.currentFood['food_id'],
                              'date': datetime.datetime.now(),
                              'food_entry_name': self.lblName.text(),
                              'serving_id': self.currentServingId,
                              'number_of_units': self.currentServingAmount,
                              'meal': 'other'})
        self.currentFood = None
        self.currentServingId = None
        self.currentServingName = None
        self.currentServingAmount = None
        self.currentFoodEntry = None
        self.doCompute()

    def doDel(self):
        self.fatsecret.q.put({'func': 'food_entry_delete',
                             'food_entry_id': self.currentFoodEntry})
        self.currentFood = None
        self.currentServingId = None
        self.currentServingName = None
        self.currentServingAmount = None
        self.currentFoodEntry = None
        self.doCompute()

    def doRefresh(self):
        self.fatsecret.q.put({'func': 'get_eaten'})
        self.fatsecret.q.put({'func': 'get_entries',
                              'date': datetime.datetime.now()})

    def doYesterday(self):
        self.fatsecret.q.put({'func': 'get_eaten'})
        self.fatsecret.q.put({'func': 'get_entries',
                              'date': datetime.datetime.today() -
                              datetime.timedelta(-1)})

    def onAmountChanged(self):
        self.doCompute()

    def doSetAmount(self):
        rwgt = self.lblScale.text()
        logging.info(rwgt)
        logging.info(self.currentFood)
        m = re.match("([0-9\.]+)g", rwgt)
        wgt = None
        if m is None:
            m = re.match("([0-9\.]+)oz", rwgt)
            if m is not None:
                wgt = float(m.group(1)) * 28.3495
        else:
            wgt = float(m.group(1))
        if wgt is not None:
            self.txtAmount.setText("%.0f" % wgt)
        else:
            self.txtAmount.setText("")

    def doCompute(self):
        if self.currentFood is None:
            self.lblName.setText("")
            self.lblServing.setText("")
        if self.currentFood is None or self.txtAmount.text() == "":
            self.btnAdd.setEnabled(False)
            self.btnDel.setEnabled(False)
            self.currentServingAmount = 0.0
            self.lblServingAmount.setText("")
            self.lblServing.setText("")
            self.lblCalories.setText("")
            self.lblProtein.setText("")
            self.lblCarbs.setText("")
            self.lblFat.setText("")
            self.btnAdd.setEnabled(False)
            self.btnDel.setEnabled(False)
            return

        wgt = float(self.txtAmount.text())
        servings = self.currentFood['servings']
        if type(servings) is dict:
            servings = servings['serving']
        if type(servings) is dict:
            servings = [servings]
        serving = servings[0]
        logging.info(serving)
        samt = float(serving['metric_serving_amount'])
        sfact = wgt / samt
        logging.info('sfact=%f', sfact)
        calories = float(serving['calories']) * sfact
        carbs = float(serving['carbohydrate']) * sfact
        protein = float(serving['protein']) * sfact
        fat = float(serving['fat']) * sfact
        self.lblCalories.setText("%.1f" % calories)
        self.lblCarbs.setText("%.1f" % carbs)
        self.lblProtein.setText("%.1f" % protein)
        self.lblFat.setText("%.1f" % fat)
        self.currentServingAmount = sfact
        self.currentServingName = serving['serving_description']
        self.lblServing.setText(self.currentServingName)
        self.lblServingAmount.setText("%.2f" % self.currentServingAmount)
        self.currentServingId = serving['serving_id']
        self.btnAdd.setEnabled(True)
        logging.info('current food entry = %s', self.currentFoodEntry)
        if self.currentFoodEntry is not None:
            self.btnDel.setEnabled(True)
        else:
            self.btnDel.setEnabled(False)

    @pyqtSlot(str)
    def onData(self, data):
        self.lblScale.setText(data)
        if self.currentFood is not None:
            self.doSetAmount()

    @pyqtSlot(QListWidgetItem)
    def eatenClick(self, item):
        logging.info('eaten click %s %s', item.text(), item.data(Qt.UserRole))
        self.lblName.setText(item.text())
        self.currentFood = self.fatsecret.foods[item.data(Qt.UserRole)]
        self.currentFoodEntry = None
        self.doCompute()

    @pyqtSlot(QTableWidgetItem)
    def todayClick(self, item):
        logging.info('today click %s %s', item.text(), item.data(Qt.UserRole))
        self.currentFood = self.fatsecret.foods[item.data(Qt.UserRole)]
        s = ''
        if 'brand_name' in self.currentFood:
            s = self.currentFood['brand_name'] + ' '
        s = s + self.currentFood['food_name']
        self.lblName.setText(s)
        self.currentServingAmount = item.data(Qt.UserRole+1)
        if self.currentServingAmount[-1:] == 'g':
            self.currentServingAmount = self.currentServingAmount[:-1]
        self.currentFoodEntry = item.data(Qt.UserRole+2)
        self.txtAmount.setText(self.currentServingAmount)
        self.doCompute()

    @pyqtSlot(dict)
    def onLogin(self, result):
        logging.info("onLogin result = %s", result)
        if self.checkError(result):
            return
        self.connected = result['login']
        if result['login']:
            self.setWindowTitle("PiFoodScale (connected)")
            self.fatsecret.q.put({'func': 'get_eaten'})
            self.fatsecret.q.put({'func': 'get_entries',
                                  'date': datetime.datetime.now()})
        else:
            self.setWindowTitle("PiFoodScale (disconnected)")

    @pyqtSlot(dict)
    def onEaten(self, result):
        logging.info("onEaten result = %s", result)
        if self.checkError(result):
            return
        self.listEaten.clear()
        for f in result['data']:
            s = ''
            if 'brand_name' in f:
                s = f['brand_name'] + ' '
            s = s + f['food_name']
            qi = QListWidgetItem(s)
            qi.setData(Qt.UserRole, f['food_id'])
            self.listEaten.addItem(qi)

    @pyqtSlot(dict)
    def onEntries(self, result):
        logging.info("onEntries result = %s", result)
        if self.checkError(result):
            return
        self.tableToday.clear()
        result = result['data']
        rows = len(result)
        totalCal = 0.0
        totalProtein = 0.0
        totalFat = 0.0
        totalCarbs = 0.0
        self.tableToday.setRowCount(rows)
        self.tableToday.setHorizontalHeaderLabels(
            ['Item', 'Qty', 'Cal', 'Protein', 'Fat', 'Carbs'])
        i = -1
        for f in result:
            i = i + 1
            food = f['food']
            entry = f['entry']
            s = ''
            if 'brand_name' in food:
                s = food['brand_name'] + ' '
            s = s + food['food_name']
            qi = QTableWidgetItem(s)
            qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            # qi.setData(Qt.UserRole, f['food_id'])
            self.tableToday.setItem(i, 0, qi)
            if 'number_of_units' in entry:
                q = float(entry['number_of_units'])
                qs = str(q)
                servid = entry['serving_id']
                servings = food['servings']['serving']
                if type(servings) is dict:
                    servings = [servings]
                for serv in servings:
                    if serv['serving_id'] == servid:
                        su = serv['metric_serving_unit']
                        sa = serv['metric_serving_amount']
                        sn = serv['number_of_units']
                        qs = "{0:.1f}".format(q * float(sa) / float(sn)) + su
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                # self.tableToday.setItem(i, 0, qi)
                qi = QTableWidgetItem(qs)
                qi.setTextAlignment(Qt.AlignHCenter)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                self.tableToday.setItem(i, 1, qi)
            if 'calories' in entry:
                totalCal += float(entry['calories'])
                qi = QTableWidgetItem(entry['calories'])
                qi.setTextAlignment(Qt.AlignHCenter)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                self.tableToday.setItem(i, 2, qi)
            if 'protein' in entry:
                totalProtein += float(entry['protein'])
                qi = QTableWidgetItem(entry['protein'])
                qi.setTextAlignment(Qt.AlignHCenter)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                self.tableToday.setItem(i, 3, qi)
            if 'fat' in entry:
                totalFat += float(entry['fat'])
                qi = QTableWidgetItem(entry['fat'])
                qi.setTextAlignment(Qt.AlignHCenter)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                self.tableToday.setItem(i, 4, qi)
            if 'carbohydrate' in entry:
                totalCarbs += float(entry['carbohydrate'])
                qi = QTableWidgetItem(entry['carbohydrate'])
                qi.setTextAlignment(Qt.AlignHCenter)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                qi.setData(Qt.UserRole, entry['food_id'])
                qi.setData(Qt.UserRole+1, qs)
                qi.setData(Qt.UserRole+2, entry['food_entry_id'])
                self.tableToday.setItem(i, 5, qi)

        self.lblTCalories.setText("%.0f" % totalCal)
        self.lblTProtein.setText("%.0f" % totalProtein)
        self.lblTCarbs.setText("%.0f" % totalCarbs)
        self.lblTFat.setText("%.0f" % totalFat)
        # self.tableToday.resizeColumnsToContents()
        # self.tableToday.resizeColumnToContents(0)

    @pyqtSlot(dict)
    def onFoodEntryCreate(self, result):
        logging.info("onFoodEntryCreate result = %s", result)
        if self.checkError(result):
            return
        self.fatsecret.q.put({'func': 'get_eaten'})
        self.fatsecret.q.put({'func': 'get_entries',
                              'date': datetime.datetime.now()})

    @pyqtSlot(dict)
    def onFoodEntryDelete(self, result):
        logging.info("onFoodEntryDelete result = %s", result)
        if self.checkError(result):
            return
        self.fatsecret.q.put({'func': 'get_eaten'})
        self.fatsecret.q.put({'func': 'get_entries',
                              'date': datetime.datetime.now()})


class ReadScale(QObject):

    data = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.zero = False
        self.oz = False
        self.value = 0
        self.neg = False
        self.predisp = ''
        self.disp = '???'
        self.emitValue()

    def emitValue(self):
        self.disp = ""
        if not self.zero:
            if self.neg:
                self.disp = '-'
            if self.oz:
                self.disp = (self.disp +
                             str(self.value/10.0))
                self.disp = self.disp + 'oz'
            else:
                self.disp = (self.disp +
                             str(self.value))
                self.disp = self.disp + 'g'
        if self.disp != self.predisp:
            logging.info('scale disp %s', self.disp)
            self.data.emit(self.disp)
            self.predisp = self.disp

    def processWindows(self):
        if (os.name == "nt"):
            import usb.core
        dev = usb.core.find(idVendor=0x0922, idProduct=0x8003)
        while(True):
            b = dev.read(0x82, 8)
            self.value = b[4] + b[5] * 256
            self.neg = (b[1] & 1) == 1
            self.zero = (b[1] & 2) == 2
            self.oz = (b[2] == 11)
            self.emitValue()

    def processPi(self):
        f = open('/dev/usb/hiddev0', 'rb')
        while(True):
            b = f.read(8)
            if (b[2] == 0x8d and b[1]) == 0x00:
                if b[0] == 0x40:
                    self.value = b[4] + b[5] * 256
                    self.emitValue()
                if b[0] == 0x5b:
                    if b[4] == 0x01:
                        self.oz = True
                    else:
                        self.oz = False
                if b[0] == 0x72:
                    if b[4] == 0x01:
                        self.zero = True
                    else:
                        self.zero = False
                if b[0] == 0x75:
                    if b[4] == 0x01:
                        self.neg = True
                    else:
                        self.neg = False

    def run(self):
        self.data.emit(self.disp)
        while(True):
            try:
                if os.name == "nt":
                    self.processWindows()
                else:
                    self.processPi()
            except:
                self.disp = "???"
                if self.disp != self.predisp:
                    logging.info('scale disp %s', self.disp)
                    self.data.emit(self.disp)
                    self.predisp = self.disp
                time.sleep(0.1)


class LogHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doRollover()


class Config():
    config = {}

    def __init__(self, name="Config.yaml"):
        self.name = name
        self.readConfig()

    def readConfig(self):
        import mergedict
        self.config = mergedict.ConfigDict(
                                yaml.load(open("Config.defaults.yaml", "r")))
        self.config.merge(yaml.load(open("Config.yaml", "r")))


class FatSecretApi(QObject):

    q = queue.Queue()

    def __init__(self, config):
        super().__init__()
        self.fsConfig = config.config['Apis']['FatSecret']
        self.foods = {}

    def run(self):
        while(True):
            item = self.q.get()
            self.dispatch(item)
            self.q.task_done()

    def dispatch(self, item):
        if item is None:
            return
        elif item['func'] == 'login':
            self.login(item)
        elif item['func'] == 'get_eaten':
            self.get_eaten(item)
        elif item['func'] == 'get_entries':
            self.get_entries(item)
        elif item['func'] == 'food_entry_create':
            self.food_entry_create(item)
        elif item['func'] == 'food_entry_delete':
            self.food_entry_delete(item)

    onLogin = pyqtSignal(dict)

    def login(self, params):
        try:
            self.fs = Fatsecret(self.fsConfig['ConsumerKey'],
                                self.fsConfig['SharedSecret'],
                                self.fsConfig['SessionToken'])
            result = self.fs.profile_get()
            self.onLogin.emit({'login': True, 'profile': result})
        except Exception as e:
            logging.exception('Fatsecret login exception:')
            self.onLogin.emit(
                {'login': False, 'error': type(e).__name__ + ': ' + str(e)})

    onEaten = pyqtSignal(dict)

    def get_eaten(self, params):
        try:
            result = self.fs.foods_get_recently_eaten()
            if result is None:
                result = []
            result3 = []
            for f in result:
                if f['food_id'] in self.foods:
                    result2 = self.foods[f['food_id']]
                else:
                    result2 = self.fs.food_get(f['food_id'])
                self.foods[f['food_id']] = result2
                result3.append(result2)
            self.onEaten.emit({'data': result3})
        except Exception as e:
            logging.exception('Fatsecret get_eaten exception:')
            self.onEaten.emit({'error': type(e).__name__ + ': ' + str(e)})

    onEntries = pyqtSignal(dict)

    def get_entries(self, params):
        try:
            result = self.fs.food_entries_get(date=params['date'])
            if result is None:
                result = []
            result3 = []
            for f in result:
                if f['food_id'] in self.foods:
                    result2 = self.foods[f['food_id']]
                else:
                    result2 = self.fs.food_get(f['food_id'])
                self.foods[f['food_id']] = result2
                result3.append({'entry': f, 'food': result2})
            self.onEntries.emit({'data': result3})
        except Exception as e:
            logging.exception('Fatsecret get_entries exception:')
            self.onEntries.emit({'error': type(e).__name__ + ': ' + str(e)})

    onFoodEntryCreate = pyqtSignal(dict)

    def food_entry_create(self, params):
        try:
            result = self.fs.food_entry_create(
                food_id=params['food_id'],
                food_entry_name=params['food_entry_name'],
                serving_id=params['serving_id'],
                number_of_units=params['number_of_units'],
                meal=params['meal'],
                date=params['date'])
            if result is None:
                result = []
            self.onFoodEntryCreate.emit({'data': result})
        except Exception as e:
            logging.exception('Fatsecret food_entry_create exception:')
            self.onFoodEntryCreate.emit(
                {'error': type(e).__name__ + ': ' + str(e)})

    onFoodEntryDelete = pyqtSignal(dict)

    def food_entry_delete(self, params):
        try:
            result = self.fs.food_entry_delete(
                food_entry_id=params['food_entry_id'])
            if result is None:
                result = []
            self.onFoodEntryCreate.emit({'data': result})
        except Exception as e:
            logging.exception('Fatsecret food_entry_delete exception:')
            self.onFoodEntryDelete.emit(
                {'error': type(e).__name__ + ': ' + str(e)})


if __name__ == '__main__':
    fmt = logging.Formatter('%(asctime)s %(message)s')
    logger = logging.getLogger()
    fileh = LogHandler(filename='PiFoodScale.log', backupCount=7)
    fileh.setFormatter(fmt)
    logger.addHandler(fileh)
    errh = logging.StreamHandler(sys.stderr)
    fileh.setFormatter(fmt)
    logger.addHandler(errh)
    logger.setLevel(logging.WARNING)
    logger.setLevel(logging.DEBUG)

    try:
        app = QApplication(sys.argv)
        try:
            config = Config()
            logging.info('config = %s', vars(config))
        except Exception as e:
            logging.exception('PiFoodScale Config Error:')
            QMessageBox.critical(
                None, "PiFoodScale Config Error",
                type(e).__name__ + ': ' + str(e), QMessageBox.Ok)
            sys.exit(1)
        ex = PiFoodScale(config)
        sys.exit(app.exec_())
    except SystemExit:
        pass
    except Exception as e:
        logging.exception('Unhandled Error Caught at outermost level:')
        QMessageBox.critical(None, "Unhandled Error",
                             type(e).__name__ + ': ' + str(e), QMessageBox.Ok)
