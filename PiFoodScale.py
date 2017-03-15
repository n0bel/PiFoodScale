import os
import sys
import time
import yaml
import logging
import logging.handlers
from PyQt5.QtCore import (QObject, QThread, pyqtSlot, pyqtSignal,
                          Qt, QVariant, QAbstractListModel,
                          QModelIndex)
from PyQt5.QtWidgets import (QWidget, QLabel, QMessageBox, QListView,
                             QPushButton, QApplication,
                             QGridLayout)
from PyQt5.QtGui import (QIcon)


class PiFoodScale(QWidget):
    config = {}
    fatsecret = None

    def __init__(self, config, fatsecret):
        super().__init__()
        self.config = config
        self.fatsecret = fatsecret
        self.initUI()

    def initUI(self):
        self.setStyleSheet('font-size: 15pt')

        btnQuit = QPushButton('Quit', self)
        btnQuit.clicked.connect(self.close)

        self.lblScale = QLabel('Scale', self)
        self.lblScale.setStyleSheet('border: 1px solid black')

        self.modelEaten = EatenListModel(self)
        self.listEaten = QListView()
        self.listEaten.setModel(self.modelEaten)
        self.listEaten.setMinimumWidth(400)
        self.listEaten.setStyleSheet("font-size: 10pt")
        self.listEaten.clicked.connect(self.eatenClick)
        # assuming the grid is 4 wide
        # and 4 high
        grid = QGridLayout()
        # line 1 is the scale
        #   row, col, rowspan, colspan
        grid.addWidget(self.lblScale, 1, 1, 1, 4)
        grid.addWidget(self.listEaten, 2, 1, 1, 4)
        grid.addWidget(btnQuit, 3, 4)

        self.setLayout(grid)

        self.setWindowTitle('PiFoodScale')
        self.setWindowIcon(QIcon('icon.jpg'))

        self.thread = QThread()
        self.reader = ReadScale(self.config)
        self.reader.data[str].connect(self.onData)
        self.reader.moveToThread(self.thread)
        self.thread.started.connect(self.reader.run)
        self.thread.start()

        self.show()
        # self.showFullScreen()

    @pyqtSlot(str)
    def onData(self, data):
        self.lblScale.setText(data)

    @pyqtSlot(QModelIndex)
    def eatenClick(self, index):
        print(index.data())
        self.modelEaten = EatenListModel(self)
        self.modelEaten.eatenList = ["fff", "ggg"]
        self.listEaten.setModel(self.modelEaten)


class EatenListModel(QAbstractListModel):
    def __init__(self, parent=None, *args):
        super().__init__(parent, *args)
        self.eatenList = ["one", "two", "three", "four",
                          "five", "six", "seven", "eight",
                          "kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.eatenList)

    def data(self, index, role):
        if index.isValid() and role == Qt.DisplayRole:
            return QVariant(self.eatenList[index.row()])
        else:
            return QVariant()


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


class FatSecretApi():

    def __init__(self, config):
        self.fsConfig = config.config['Apis']['FatSecret']

    def login(self):
        from fatsecret import Fatsecret

        self.fs = Fatsecret(self.fsConfig['ConsumerKey'],
                            self.fsConfig['SharedSecret'],
                            self.fsConfig['SessionToken'])

        # params = {'method': 'foods.get_favorites', 'format': 'json'}
        # response = self.fs.session.get(self.fs.api_url, params=params)
        # print(response.json())
        # return self.fs.valid_response(response)


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
            print(vars(config))
        except Exception as e:
            logging.exception('PiFoodScale Config Error:')
            QMessageBox.critical(None, "PiFoodScale Config Error",
                                 str(e), QMessageBox.Ok)
            sys.exit(1)
        try:
            fatsecret = FatSecretApi(config)
            fatsecret.login()
        except Exception as e:
            logging.exception('PiFoodScale FatSecret Connect Error:')
            QMessageBox.critical(None, "PiFoodScale FatSecret Connect Error",
                                 str(e), QMessageBox.Ok)
            sys.exit(1)
        ex = PiFoodScale(config, fatsecret)
        sys.exit(app.exec_())
    except SystemExit:
        pass
    except Exception as e:
        logging.exception('Unhandled Error Caught at outermost level:')
        QMessageBox.critical(None, "Unhandled Error",
                             str(e), QMessageBox.Ok)
