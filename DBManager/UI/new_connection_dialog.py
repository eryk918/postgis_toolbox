from typing import Dict

from qgis.PyQt.QtCore import QRegExp
from qgis.PyQt.QtGui import QRegExpValidator
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings
from qgis.core import Qgis

from ...utils import QMessageBox, make_query, os, create_pg_connecton, tr, test_query,\
    connection_key_names, conn_key_string, plugin_name

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'new_connection_dialog.ui'))


class NewPGConnectionDialog(QDialog, FORM_CLASS):

    def __init__(self, conn_name=None, parent=None):
        super(NewPGConnectionDialog, self).__init__(parent)
        self.setupUi(self)
        self.set_up_signals()
        self.conn_name = conn_name
        if conn_name:
            self.fill_dlg_info(conn_name)

    def accept(self) -> None:
        if not self.conn_name_lineEdit.text():
            QMessageBox.warning(self, plugin_name, tr('Connection name is required!'), QMessageBox.Ok)
            return
        super(NewPGConnectionDialog, self).accept()

    def set_up_signals(self) -> None:
        self.settings_widget.setDataprovider('postgres')
        self.settings_widget.showStoreCheckboxes(True)
        self.btnConnect.clicked.connect(self.test_connection)

    def fill_dlg_info(self, conn_name: str) -> None:
        settings_object = QSettings()
        key_string = f"{conn_key_string}{conn_name}"
        self.service_name_lineEdit.setText(settings_object.value(f"{key_string}/service"))
        self.host_name_lineEdit.setText(settings_object.value(f"{key_string}/host"))
        self.port_lineEdit.setText(settings_object.value(f"{key_string}/port"))
        self.database_lineEdit.setText(settings_object.value(f"{key_string}/database"))
        value_idx = self.ssl_mode_combo.findText(settings_object.value(f"{key_string}/sslmode"))
        if value_idx != -1:
            self.ssl_mode_combo.setCurrentIndex(value_idx)
        if settings_object.value(f"{key_string}/saveUsername") == 'true':
            self.settings_widget.setUsername(settings_object.value(f"{key_string}/username"))
            self.settings_widget.setStoreUsernameChecked(True)
        if settings_object.value(f"{key_string}/savePassword") == 'true':
            self.settings_widget.setPassword(settings_object.value(f"{key_string}/password"))
            self.settings_widget.setStorePasswordChecked(True)
        self.settings_widget.setConfigId(settings_object.value(f"{key_string}/authcfg"))
        self.conn_name_lineEdit.setText(conn_name)
        self.conn_name_lineEdit.setValidator(QRegExpValidator(QRegExp("[^\\/]*")))

    def test_connection(self) -> None:
        test_db = create_pg_connecton({'connection_name': self.conn_name_lineEdit.text(),
                                       'host': self.host_name_lineEdit.text(),
                                       'database': self.database_lineEdit.text(), 'port': self.port_lineEdit.text(),
                                       'username': self.settings_widget.username(),
                                       'password': self.settings_widget.password()})
        if test_db.isValid() and test_db.isOpen() and make_query(test_db, test_query):
            self.bar.pushMessage(tr(f"Connection to {self.conn_name_lineEdit.text()} was successful."), Qgis.Info)
        else:
            self.bar.pushMessage(tr("Connection failed - consult message log for details."), Qgis.Warning)

    def save_conn(self) -> Dict[str, Dict[str, str]]:
        settings = QSettings()
        if self.conn_name:
            settings.remove(f"{conn_key_string}{self.conn_name}")
            settings.sync()
        key_string = f"{conn_key_string}{self.conn_name_lineEdit.text()}"
        settings.setValue(f"{key_string}/service", self.service_name_lineEdit.text())
        settings.setValue(f"{key_string}/host", self.host_name_lineEdit.text())
        settings.setValue(f"{key_string}/port", self.port_lineEdit.text())
        settings.setValue(f"{key_string}/database", self.database_lineEdit.text())
        if self.settings_widget.storeUsernameIsChecked():
            settings.setValue(f"{key_string}/username", self.settings_widget.username())
        if self.settings_widget.storePasswordIsChecked():
            settings.setValue(f"{key_string}/password", self.settings_widget.password())
        settings.setValue(f"{key_string}/authcfg", self.settings_widget.configId())
        settings.setValue(f"{key_string}/sslmode", self.ssl_mode_combo.currentText())
        settings.setValue(f"{key_string}/saveUsername",
                          "true" if self.settings_widget.storeUsernameIsChecked() else "false")
        settings.setValue(f"{key_string}/savePassword",
                          "true" if self.settings_widget.storePasswordIsChecked() else "false")
        return {
            self.conn_name_lineEdit.text(): {**{key_name: settings.value(f'{key_string}/{key_name}')
                                                for key_name in connection_key_names},
                                             'connection_name': self.conn_name_lineEdit.text()}}
