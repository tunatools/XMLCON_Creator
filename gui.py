import os
import sys
import pathlib

from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QGridLayout,
    QComboBox,
    QWidget,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtGui import QIcon
import resources

import ctypes

import yaml
import xml.etree.ElementTree as ET

# https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7/1552105#1552105
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TUNATools")


'''
When build with PyInstaller, static files are  moved to a temp folder
and the path is saved in _MEIPASS. This function gets the file from that folder
if it doesn't exist (because we're running the non build py file), it get's
the local version!

'''
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


'''
Config and settings are saved to %APPDATA% so they can be edited. The original
files are only used as templates. They are not edited so broken files can
simply be deleted and will be rebuild in a functional form.  
'''
appdata_location = pathlib.Path(os.getenv('LOCALAPPDATA'), 'TunaTools')
if not appdata_location.is_dir():
    os.mkdir(appdata_location)
config_yaml = pathlib.Path(appdata_location, 'config.yaml')
settings_location = pathlib.Path(appdata_location, "settings.yaml")
default_xmlcon = pathlib.Path(appdata_location, "default.xmlcon")

if not config_yaml.is_file():
    import shutil
    default_config_yaml = resource_path('config.yaml')
    shutil.copyfile(default_config_yaml, config_yaml)

if not settings_location.is_file():
    default_channels = [None]*13
    default_sensor_location = "./Sensors"
    if not pathlib.Path(default_sensor_location).is_dir():
        # Ask user where the file is and save settings
        # This will be editable later
        pass

if not default_xmlcon.is_file():
    import shutil
    default_xml = resource_path('default.xmlcon')
    shutil.copyfile(default_xml, default_xmlcon)




class Sensor:
    def __init__(self, type, serial_number, params):
        self.type = type
        self.sn = serial_number
        self.params = params

    def print_params(self):
        return ET.tostring(self.params, encoding='unicode')

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f'{self.sn} ({self.type})'

    def save(self, folder):
        et = ET.ElementTree(self.params)
        et.write(f'{folder}/{self}.xml', encoding="utf-8")

class Settings:
    def __init__(self):
        # {sensor_serialnumber: Sensor_obj}
        self.sensors = dict()
        self.channels = dict()
        self.default_channels = [None]*13
        self.sensor_folder = pathlib.Path('./Sensors')
        self._config()
        self.set_settings()

    def _config(self, file=config_yaml):
        with open(file, 'r') as yaml_file:
            config = yaml.safe_load(yaml_file)
        self.channels = config['channels']
        # SBE CTD 911 specific
        assert len(self.channels) == 13

    def set_settings(self, file=settings_location):
        if pathlib.Path(file).is_file():
            with open(file, 'r') as yaml_file:
                data = yaml.safe_load(yaml_file)
            self.default_channels = data['Channels']
            self.sensor_folder = pathlib.Path(data['Sensors_folder'])
            assert self.sensor_folder.is_dir()

            self.sensors = dict()
            for root, dirs, files in os.walk(self.sensor_folder):
                for name in files:
                    possible_sensor = pathlib.Path(root, name)
                    if possible_sensor.suffix.lower() == '.xml':
                        try:
                            sensor = self.get_sensor_from_file(possible_sensor)
                        except: # What errors can happen here? Not valid XML
                            # skip if not parsed!
                            pass
                        if str(sensor) not in self.sensors:
                            self.sensors[str(sensor)] = sensor
                        else:
                            # care with overwriting (what happens if we have 2 sensors
                            pass #? Get newer one?


    def get_sensor_from_file(self, file):
        tree = ET.parse(file)
        root = tree.getroot()
        # Assert it has all this
        sensor = Sensor(root.tag, root.find('SerialNumber').text, root)
        return sensor


    def write_sensors(self, list_of_sensors, default=default_xmlcon):
        xmlcon = ET.parse(default).getroot()
        for sensor in list_of_sensors:
            self._insert_sensor(xmlcon, sensor.params)
        return xmlcon

    def _insert_sensor(self, tree, sensor):
        sensor_array = tree.find('.//SensorArray')
        array_size = int(sensor_array.get('Size'))
        sensor_array.set('Size', str(array_size + 1))
        sensor_tag = ET.SubElement(sensor_array, 'Sensor')
        sensor_tag.set('index', str(array_size))
        sensor_tag.set('SensorID', sensor.get('SensorID'))
        sensor_tag.extend([sensor])

    def import_xmlcon(self, file):
        tree = ET.parse(file)
        root = tree.getroot()
        sensor_xmls = root.findall('.//SensorArray/Sensor/*')
        sensors = [Sensor(sensor.tag, sensor.find('SerialNumber').text, sensor) for sensor in sensor_xmls]
        new_sensors = [sensor for sensor in sensors if str(sensor) not in self.sensors.keys()]
        if not self.sensor_folder.is_dir():
            os.mkdir(self.sensor_folder)
        for sensor in new_sensors:
            sensor.save(self.sensor_folder)
            self.sensors[str(sensor)] = sensor
        return new_sensors

    def save(self):
        with open(settings_location, 'w') as yaml_file:
            dump = yaml.dump({'Sensors_folder': str(self.sensor_folder), 'Channels': self.default_channels})
            yaml_file.write(dump)
        self.set_settings()


class Window(QMainWindow):
    def __init__(self):
        self.settings = Settings()
        super().__init__(parent=None)
        self.setWindowTitle("TUNATools")
        self._createMenu()
        self.active_widget = None
        self._showMain()
        import ctypes
        self.setWindowIcon(QIcon(':/icons/icon'))

    def _createMenu(self):
        menu = self.menuBar()
        file = menu.addMenu("&Menu")

        import_action = file.addAction("&Import", self._showImport)

        file.addAction(import_action)

        file.addAction("E&xit", self.close)

        view = menu.addMenu("&View")
        view.addAction('&Create', self._showMain)
        view.addAction('&Sensors', self._showSensors)

        settings = menu.addMenu("Settings")
        settings.addAction('Edit', self._showSettings)

    def _createComboBox(self, options, default=None):
        combobox = QComboBox(placeholderText="Choose a sensor")
        option_type = options['type']
        option_list = options['values']
        if any(self.settings.default_channels):
            pass
        # assert all([option in all_sensors for option in options])
        index = 0
        for sn, sensor in sorted(self.settings.sensors.items()):
            if option_type == "include":
                if option_list and sensor.type in option_list:
                    combobox.addItem(sn)
                    if default == sn:
                        combobox.setCurrentIndex(index)
                    index += 1
            elif option_type == "exclude":
                if not option_list or sensor.type not in option_list:
                    combobox.addItem(sn)
                    if default == str(sensor):
                        combobox.setCurrentIndex(index)
                    index += 1
        return combobox


    def _createMainWidget(self):
        widget = QWidget()
        layout = QGridLayout()
        widget.setLayout(layout)

        for i, item in enumerate(self.settings.channels.items()):
            k, v = item
            layout.addWidget(QLabel(k), i, 0)
            layout.addWidget(self._createComboBox(v, default=self.settings.default_channels[i]), i, 1)

        button = QPushButton('Create XMLCON')
        button.clicked.connect(lambda _: self.writeXMLCON(self.createXMLCON()))
        layout.addWidget(button, i+2, 0, 1, 2)
        # Add location to save! (timestamped?)
        return widget

    def _createSettings(self):
        widget = QWidget()
        layout = QGridLayout()
        widget.setLayout(layout)
        label = QLabel(f"We are currently trying to find sensors in\n{self.settings.sensor_folder.absolute()}")
        layout.addWidget(label)
        button = QPushButton('Choose a different Sensor folder')
        layout.addWidget(button)
        button.clicked.connect(lambda _: self._chooseSettingsFolder(label))
        return widget

    def _createSensors(self):
        widget = QWidget()
        layout = QGridLayout()
        widget.setLayout(layout)
        for i, sensor in enumerate(sorted(self.settings.sensors.values(), key=lambda s: str(s))):
            button = QPushButton(f'Sensor {sensor.sn}')
            layout.addWidget(button, i, 0)
            button.clicked.connect(lambda _, sensor=sensor: self._sensor_popup(sensor))
        return widget

    def _importSensors(self):
        file, type = QFileDialog.getOpenFileName(self, "Select file", filter="XMLCON file (*.xmlcon)")
        if file:
            assert type == "XMLCON file (*.xmlcon)"
            new_sensors = self.settings.import_xmlcon(file)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            if new_sensors:
                msg.setText(f'New sensors:\n{", ".join(map(str,new_sensors))}')
            else:
                msg.setText('We already had those sensors!')
            msg.setWindowTitle("New sensors")
            msg.exec()

    def _createImport(self):
        widget = QWidget()
        layout = QGridLayout()
        widget.setLayout(layout)
        button = QPushButton('Import XMLCON')
        layout.addWidget(button)
        button.clicked.connect(self._importSensors)
        return widget


    def _sensor_popup(self, sensor):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f'Data for sensor {sensor.sn}')
        msg.setInformativeText(f'{sensor.print_params()}')
        msg.setWindowTitle("Sensor data")
        msg.exec()

    def _chooseSettingsFolder(self, label):
        folder = QFileDialog.getExistingDirectory (self, "Select your sensor folder")
        if folder:
            self.settings.sensor_folder = pathlib.Path(folder)
            self.settings.save()
            label.setText(f'Loaded settings file {folder}')

    def _showSettings(self):
        self.active_widget = self._createSettings()
        self.setCentralWidget(self.active_widget)

    def _showMain(self):
        self.active_widget = self._createMainWidget()
        self.setCentralWidget(self.active_widget)

    def _showSensors(self):
        self.active_widget = self._createSensors()
        self.setCentralWidget(self.active_widget)

    def _showImport(self):
        self.active_widget = self._createImport()
        self.setCentralWidget(self.active_widget)


    def createXMLCON(self, settings=settings_location):
        channels = [x for x in self.active_widget.children() if type(x) == QComboBox]
        empty_channels = [channel for channel in channels if channel.currentText() == '']
        if empty_channels:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("Empty chanels")
            msg.setInformativeText('Please be sure to set all channels. If there is nothing. Please set an empty channel')
            msg.setWindowTitle("Error")
            msg.exec()
            return None
        else:
            self.settings.default_channels = [c.currentText() for c in channels]
            self.settings.save()
            final_xml = self.settings.write_sensors([self.settings.sensors[channel.currentText()] for channel in channels])
            return final_xml

    def writeXMLCON(self, xmlcon, file=None):
        if xmlcon:
            if file:
                file_location = file
            else:
                file_location, _ = QFileDialog.getSaveFileName(filter="XMLCON file (*.xmlcon)")
                assert _ == "XMLCON file (*.xmlcon)"
            if file_location:
                tree = ET.ElementTree(xmlcon)
                tree.write(file_location, encoding='utf-8')
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setInformativeText(f'The xmlcon {file_location} was created')
                msg.setWindowTitle("Created")
                msg.exec()


if __name__ == "__main__":
    app = QApplication([])
    window = Window()
    window.show()
    sys.exit(app.exec())