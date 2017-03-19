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
                             QGridLayout, QListWidgetItem, QTableWidgetItem)
from PyQt5.QtGui import (QIcon)


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
        self.fatsecret.moveToThread(self.fsThread)
        self.fsThread.started.connect(self.fatsecret.run)
        self.fsThread.start()
        self.fatsecret.q.put({'func': 'login'})
        self.fatsecret.q.put({'func': 'get_entries',
                              'date': datetime.datetime.now()})

    def initUI(self):
        self.setStyleSheet('font-size: 15pt')

        btnQuit = QPushButton('Quit', self)
        btnQuit.clicked.connect(self.close)

        self.lblScale = QLabel('Scale', self)
        self.lblScale.setStyleSheet('border: 1px solid black')

        self.listEaten = QListWidget()
        self.listEaten.setMinimumWidth(600)
        self.listEaten.setMaximumHeight(200)
        self.listEaten.setStyleSheet("font-size: 10pt")
        self.listEaten.itemClicked.connect(self.eatenClick)

        self.tableToday = QTableWidget()
        self.tableToday.setStyleSheet("font-size: 10pt")
        self.tableToday.setMinimumWidth(600)
        self.tableToday.itemClicked.connect(self.todayClick)

        self.lblAmount = QLabel('', self)
        self.lblName = QLabel('', self)

        self.lblCalories = QLabel('', self)
        self.lblProtein = QLabel('', self)
        self.lblFat = QLabel('', self)
        self.lblCarbs = QLabel('', self)

        self.lblTCalories = QLabel('', self)
        self.lblTProtein = QLabel('', self)
        self.lblTFat = QLabel('', self)
        self.lblTCarbs = QLabel('', self)

        grid = QGridLayout()
        # line 1 is the scale
        #   row, col, rowspan, colspan
        grid.addWidget(self.lblScale, 1, 1, 1, 5)

        grid.addWidget(self.lblAmount,           2, 1, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblName,             2, 2, 1, 4)

        grid.addWidget(QLabel('Calories', self), 3, 2, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Protein', self),  3, 3, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Fat', self),      3, 4, 1, 1, Qt.AlignCenter)
        grid.addWidget(QLabel('Carbs', self),    3, 5, 1, 1, Qt.AlignCenter)

        grid.addWidget(QLabel('This', self),     4, 1, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblCalories,         4, 2, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblProtein,          4, 3, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblFat,              4, 4, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblCarbs,            4, 5, 1, 1, Qt.AlignRight)

        grid.addWidget(QLabel('Today', self),    5, 1, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblTCalories,        5, 2, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblTProtein,         5, 3, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblTFat,             5, 4, 1, 1, Qt.AlignRight)
        grid.addWidget(self.lblTCarbs,           5, 5, 1, 1, Qt.AlignRight)

        grid.addWidget(self.tableToday, 6, 1, 1, 5)
        grid.addWidget(self.listEaten, 7, 1, 1, 5)
        grid.addWidget(btnQuit, 8, 5)

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

    def doCompute(self):
        rwgt = self.lblScale.text()
        print(rwgt)
        print(self.currentFood)
        m = re.match("([0-9\.]+)g", rwgt)
        if m is not None:
            wgt = float(m.group(1))
            servings = self.currentFood['servings']
            if type(servings) is dict:
                servings = servings['serving']
            if type(servings) is dict:
                servings = [servings]
            serving = servings[0]
            print(serving)
            samt = float(serving['metric_serving_amount'])
            sfact = wgt / samt
            print('sfact=', sfact)
            calories = float(serving['calories']) * sfact
            carbs = float(serving['carbohydrate']) * sfact
            protein = float(serving['protein']) * sfact
            fat = float(serving['fat']) * sfact
            self.lblAmount.setText("%.0f" % wgt)
            self.lblCalories.setText("%.1f" % calories)
            self.lblCarbs.setText("%.1f" % carbs)
            self.lblProtein.setText("%.1f" % protein)
            self.lblFat.setText("%.1f" % fat)
        else:
            self.lblAmount.setText("")
            self.lblCalories.setText("")
            self.lblProtein.setText("")
            self.lblCarbs.setText("")
            self.lblFat.setText("")

    @pyqtSlot(str)
    def onData(self, data):
        self.lblScale.setText(data)
        if self.currentFood is not None:
            self.doCompute()

    @pyqtSlot(QListWidgetItem)
    def eatenClick(self, item):
        print(item.text(), item.data(Qt.UserRole))
        self.lblName.setText(item.text())
        self.currentFood = self.fatsecret.foods[item.data(Qt.UserRole)]
        self.doCompute()

    @pyqtSlot(QTableWidgetItem)
    def todayClick(self, item):
        print(item.text())

    @pyqtSlot(dict)
    def onLogin(self, result):
        # print("onLogin result =", result)
        if self.checkError(result):
            return
        self.connected = result['login']
        if result['login']:
            self.setWindowTitle("PiFoodScale (connected)")
            self.fatsecret.q.put({'func': 'get_eaten'})
        else:
            self.setWindowTitle("PiFoodScale (disconnected)")

    @pyqtSlot(dict)
    def onEaten(self, result):
        # print("onEaten result =", result)
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
        print("onEntries result =", result)
        if self.checkError(result):
            return
        self.tableToday.clear()
        result = result['data']
        rows = len(result)
        self.tableToday.setColumnCount(3)
        self.tableToday.setHorizontalHeaderLabels(['Item', 'Qty', 'Cal'])
        self.tableToday.setRowCount(rows)
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
                servings = food['servings']
                if type(servings) is dict:
                    servings = servings['serving']
                if type(servings) is dict:
                    servings = [servings]
                for serv in servings:
                    sss = serv['serving']
                    if sss['serving_id'] == servid:
                        su = sss['metric_serving_unit']
                        sa = sss['metric_serving_amount']
                        qs = "{0:.1f}".format(q * float(sa)) + su
                qi = QTableWidgetItem(qs)
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.tableToday.setItem(i, 1, qi)
            if 'calories' in entry:
                qi = QTableWidgetItem(entry['calories'])
                qi.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.tableToday.setItem(i, 2, qi)

        self.tableToday.resizeColumnsToContents()


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
            print(self.disp)
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
                    print(self.disp)
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
                                yaml.load(open("Config.Defaults.yaml", "r")))
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
            self.onLogin.emit({'login': False, 'error': str(e)})

    onEaten = pyqtSignal(dict)

    def get_eaten(self, params):
        try:
            result = self.fs.foods_get_recently_eaten()
            if result is None:
                result = []
            result3 = []
            for f in result:
                result2 = self.fs.food_get(f['food_id'])
                self.foods[f['food_id']] = result2
                result3.append(result2)
            self.onEaten.emit({'data': result3})
        except Exception as e:
            logging.exception('Fatsecret get_eaten exception:')
            self.onEaten.emit({'error': str(e)})

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
            self.onEntries.emit({'error': str(e)})


if __name__ == '__main__':
    fmt = logging.Formatter('%(asctime)s %(message)s')
    logger = logging.getLogger()
    fileh = LogHandler(filename='PiFoodScale.log', backupCount=7)
    fileh.setLevel(logging.DEBUG)
    fileh.setFormatter(fmt)
    logger.addHandler(fileh)
    errh = logging.StreamHandler(sys.stderr)
    errh.setLevel(logging.DEBUG)
    fileh.setFormatter(fmt)
    logger.addHandler(errh)
    try:
        app = QApplication(sys.argv)
        try:
            config = Config()
            # print(vars(config))
        except Exception as e:
            logging.exception('PiFoodScale Config Error:')
            QMessageBox.critical(None, "PiFoodScale Config Error",
                                 str(e), QMessageBox.Ok)
            sys.exit(1)
        ex = PiFoodScale(config)
        sys.exit(app.exec_())
    except SystemExit:
        pass
    except Exception as e:
        logging.exception('Unhandled Error Caught at outermost level:')
        QMessageBox.critical(None, "Unhandled Error",
                             str(e), QMessageBox.Ok)
