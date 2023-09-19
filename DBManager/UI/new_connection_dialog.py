from typing import Dict

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QRegExp
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QRegExpValidator
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import Qgis, QgsMessageLog

from ..db_utils.db_utils import ssl_modes, ssl_modes_enum
from ...utils import QMessageBox, make_query, os, create_pg_connecton, tr, \
    test_query, connection_key_names, conn_key_string, plugin_name, \
    repair_dialog, invert_dict

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'new_connection_dialog.ui'))


class NewPGConnectionDialog(QDialog, FORM_CLASS):

    def __init__(self, conn_name=None, parent=None):
        super(NewPGConnectionDialog, self).__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'manage_dbs.png')
        self.set_up_signals()
        self.setup_default_data()
        self.conn_name = conn_name
        if conn_name:
            self.fill_dlg_info(conn_name)

    def accept(self) -> None:
        required_fields = (
            self.conn_name_lineEdit.text(),
            self.host_name_lineEdit.text(),
            self.port_lineEdit.text(),
            self.database_lineEdit.text()
        )

        if not all(required_fields):
            QMessageBox.warning(
                self, plugin_name,
                tr('Please fill in the required fields.'),
                QMessageBox.Ok
            )
            return
        super(NewPGConnectionDialog, self).accept()

    def set_up_signals(self) -> None:
        self.settings_widget.setDataprovider('postgres')
        self.settings_widget.showStoreCheckboxes(True)
        self.btnConnect.clicked.connect(self.test_connection)

    def setup_default_data(self) -> None:
        self.ssl_mode_combo.clear()
        self.ssl_mode_combo.addItems(ssl_modes.keys())

    def fill_dlg_info(self, conn_name: str) -> None:
        settings_object = QSettings()
        key_string = f"{conn_key_string}{conn_name}"
        service_data = settings_object.value(f"{key_string}/service")
        self.service_name_lineEdit.setText(service_data if isinstance(service_data, str) else '')
        self.host_name_lineEdit.setText(settings_object.value(f"{key_string}/host"))
        port_value = settings_object.value(f"{key_string}/port")
        if port_value and str(port_value).isdigit():
            self.port_lineEdit.setText(str(settings_object.value(f"{key_string}/port")))
        else:
            self.port_lineEdit.setText('5432')
        self.database_lineEdit.setText(settings_object.value(f"{key_string}/database"))
        ssl_value = settings_object.value(f"{key_string}/sslmode")

        if ssl_value is not None and (isinstance(ssl_value, int) or ssl_value.isdigit()):
            self.ssl_mode_combo.setCurrentText(ssl_modes_enum[ssl_value if isinstance(ssl_value, int) else int(ssl_value)])
        elif isinstance(ssl_value, str) and ssl_value:
            self.ssl_mode_combo.setCurrentText(invert_dict(ssl_modes)[ssl_value])
        if settings_object.value(f"{key_string}/saveUsername") == 'true':
            self.settings_widget.setUsername(settings_object.value(f"{key_string}/username"))
            self.settings_widget.setStoreUsernameChecked(True)
        if settings_object.value(f"{key_string}/savePassword") == 'true':
            self.settings_widget.setPassword(settings_object.value(f"{key_string}/password"))
            self.settings_widget.setStorePasswordChecked(True)
        config_id_data = settings_object.value(f"{key_string}/authcfg")
        self.settings_widget.setConfigId(config_id_data if isinstance(config_id_data, str) else '')
        self.conn_name_lineEdit.setText(conn_name)
        self.conn_name_lineEdit.setValidator(QRegExpValidator(QRegExp("[^\\/]*")))

    def test_connection(self) -> None:
        port_value = self.port_lineEdit.text()
        if not port_value or not port_value.isdigit():
            self.port_lineEdit.setText('5432')
        test_db = create_pg_connecton(
            {
                'connection_name': self.conn_name_lineEdit.text(),
                'host': self.host_name_lineEdit.text(),
                'database': self.database_lineEdit.text(),
                'port': self.port_lineEdit.text(),
                'username': self.settings_widget.username(),
                'password': self.settings_widget.password()
            }
        )
        if test_db.isValid() and test_db.isOpen() \
                and make_query(test_db, test_query):
            self.bar.pushMessage(tr(
                f"Connection to {self.conn_name_lineEdit.text()} "
                f"was successful."),
                Qgis.Info)
        else:
            self.bar.pushMessage(
                tr("Connection failed - consult message log for details."),
                Qgis.Warning)
            QgsMessageLog.logMessage(
                test_db.lastError().text(), level=Qgis.Critical,
                tag=plugin_name)

    def save_conn(self) -> Dict[str, Dict[str, str]]:
        settings = QSettings()
        if self.conn_name:
            settings.remove(f"{conn_key_string}{self.conn_name}")
            settings.sync()
        key_string = f"{conn_key_string}{self.conn_name_lineEdit.text()}"
        settings.setValue(f"{key_string}/service", self.service_name_lineEdit.text())
        settings.setValue(f"{key_string}/host", self.host_name_lineEdit.text())
        port_value = self.port_lineEdit.text()
        if not port_value or not port_value.isdigit():
            port_value = '5432'
        settings.setValue(f"{key_string}/port", port_value)
        settings.setValue(f"{key_string}/database",
                          self.database_lineEdit.text())
        if self.settings_widget.storeUsernameIsChecked():
            settings.setValue(f"{key_string}/username", self.settings_widget.username())
        if self.settings_widget.storePasswordIsChecked():
            settings.setValue(f"{key_string}/password", self.settings_widget.password())
        settings.setValue(f"{key_string}/authcfg", self.settings_widget.configId())
        settings.setValue(f"{key_string}/sslmode", ssl_modes[self.ssl_mode_combo.currentText()])
        settings.setValue(f"{key_string}/saveUsername", "true" if self.settings_widget.storeUsernameIsChecked() else "false")
        settings.setValue(f"{key_string}/savePassword", "true" if self.settings_widget.storePasswordIsChecked() else "false")
        return {
            self.conn_name_lineEdit.text(): {
                **{key_name: settings.value(f'{key_string}/{key_name}')
                   for key_name in connection_key_names},
                'connection_name': self.conn_name_lineEdit.text()}}
