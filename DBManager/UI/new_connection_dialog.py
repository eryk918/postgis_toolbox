from qgis.PyQt import uic
from qgis.PyQt.QtCore import QRegularExpression
from qgis.PyQt.QtGui import QRegularExpressionValidator
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import Qgis, QgsDataSourceUri

from ..db_utils.db_utils import ssl_modes
from ...utils import os, tr, plugin_name, repair_dialog, show_warning, \
    invert_dict, postgres_metadata, create_connection_from_uri, \
    check_connection

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'new_connection_dialog.ui'))


class NewPGConnectionDialog(QDialog, FORM_CLASS):

    def __init__(self, conn_name=None, parent=None):
        super(NewPGConnectionDialog, self).__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'manage_dbs.svg')
        self.set_up_signals()
        self.setup_default_data()
        self.conn_name = conn_name
        self.conn_name_lineEdit.setValidator(
            QRegularExpressionValidator(QRegularExpression("[^\\/]*")))
        if conn_name:
            self.fill_dlg_info(conn_name)

    def accept(self) -> None:
        required_fields = (
            self.conn_name_lineEdit.text(),
            self.host_name_lineEdit.text() or self.service_name_lineEdit.text(),
            self.database_lineEdit.text()
        )
        if not all(required_fields):
            show_warning(
                self,
                tr('Please fill in the required fields.'))
            return
        super(NewPGConnectionDialog, self).accept()

    def set_up_signals(self) -> None:
        self.settings_widget.setDataprovider('postgres')
        self.settings_widget.showStoreCheckboxes(True)
        self.btnConnect.clicked.connect(self.test_connection)

    def setup_default_data(self) -> None:
        self.ssl_mode_combo.clear()
        self.ssl_mode_combo.addItems(ssl_modes.keys())
        self.ssl_mode_combo.setCurrentText(
            invert_dict(ssl_modes)[QgsDataSourceUri.SslPrefer])
        self.port_lineEdit.setText('5432')

    def fill_dlg_info(self, conn_name: str) -> None:
        connection = postgres_metadata().findConnection(conn_name)
        if connection is None:
            self.conn_name_lineEdit.setText(conn_name)
            return
        uri = QgsDataSourceUri(connection.uri())
        configuration = connection.configuration()
        self.conn_name_lineEdit.setText(conn_name)
        self.service_name_lineEdit.setText(uri.service())
        self.host_name_lineEdit.setText(uri.host())
        self.port_lineEdit.setText(uri.port() or '5432')
        self.database_lineEdit.setText(uri.database())
        self.ssl_mode_combo.setCurrentText(
            invert_dict(ssl_modes).get(uri.sslMode(), tr('prefer')))
        if configuration.get('saveUsername') in (True, 'true'):
            self.settings_widget.setUsername(uri.username())
            self.settings_widget.setStoreUsernameChecked(True)
        if configuration.get('savePassword') in (True, 'true'):
            self.settings_widget.setPassword(uri.password())
            self.settings_widget.setStorePasswordChecked(True)
        self.settings_widget.setConfigId(uri.authConfigId())

    def build_uri(self) -> QgsDataSourceUri:
        uri = QgsDataSourceUri()
        port_value = self.port_lineEdit.text()
        if not port_value.isdigit():
            port_value = '5432'
            self.port_lineEdit.setText(port_value)
        ssl_mode = ssl_modes[self.ssl_mode_combo.currentText()]
        if self.service_name_lineEdit.text():
            uri.setConnection(
                self.service_name_lineEdit.text(),
                self.database_lineEdit.text(),
                self.settings_widget.username(),
                self.settings_widget.password(),
                ssl_mode, self.settings_widget.configId())
        else:
            uri.setConnection(
                self.host_name_lineEdit.text(), port_value,
                self.database_lineEdit.text(),
                self.settings_widget.username(),
                self.settings_widget.password(),
                ssl_mode, self.settings_widget.configId())
        return uri

    def test_connection(self) -> None:
        connection = create_connection_from_uri(self.build_uri().uri(False))
        if check_connection(connection):
            self.bar.pushMessage(
                tr('Connection to {0} was successful.').format(
                    self.conn_name_lineEdit.text()),
                Qgis.Info)
        else:
            self.bar.pushMessage(
                tr("Connection failed - consult message log for details."),
                Qgis.Warning)

    def save_conn(self) -> str:
        new_name = self.conn_name_lineEdit.text()
        metadata = postgres_metadata()
        if self.conn_name and self.conn_name != new_name:
            metadata.deleteConnection(self.conn_name)
        uri = self.build_uri()
        if not self.settings_widget.storeUsernameIsChecked():
            uri.setUsername('')
        if not self.settings_widget.storePasswordIsChecked():
            uri.setPassword('')
        configuration = {
            'saveUsername': self.settings_widget.storeUsernameIsChecked(),
            'savePassword': self.settings_widget.storePasswordIsChecked()
        }
        connection = metadata.createConnection(uri.uri(False), configuration)
        connection.store(new_name)
        return new_name
