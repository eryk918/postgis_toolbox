# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtCore import QSettings

from .UI.db_manager_menu import DBManagerMenu_UI
from ..utils import project, iface, connection_key_names, create_pg_connecton, \
    make_query, plugin_name, test_query, QMessageBox


class DBManager:
    def __init__(self, parent):
        self.main = parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        self.actual_crs = project.crs().postgisSrid()
        self.plugin_dir = self.main.plugin_dir

    def run(self) -> None:
        self.dlg = DBManagerMenu_UI(self)
        self.dlg.setup_dialog()
        self.fetch_connections()
        self.dlg.run_dialog()

    def fetch_connections(self) -> None:
        self.connections_dict = {}
        base_group_name = 'PostgreSQL/connections'
        settings_object = QSettings()
        settings_object.beginGroup(base_group_name)
        for connection_name in settings_object.childGroups():
            tmp_dict = {}
            settings_object = QSettings()
            settings_object.beginGroup(f"{base_group_name}/{connection_name}")
            connection_keys = settings_object.childKeys()
            for connection_parameter in connection_key_names:
                if connection_parameter in connection_keys:
                    tmp_dict[connection_parameter] = \
                        settings_object.value(connection_parameter)
                elif connection_parameter == 'connection_name':
                    tmp_dict[connection_parameter] = connection_name
            self.connections_dict[connection_name] = tmp_dict
        self.dlg.connection_cbbx.clear()
        self.dlg.connection_cbbx.addItems(list(self.connections_dict))

    def connect_server(self) -> None:
        current_server = self.dlg.connection_cbbx.currentText()
        connection_parameters = self.connections_dict[current_server]
        self.db = create_pg_connecton(connection_parameters)
        if self.db.isValid() and self.db.isOpen() and \
                make_query(self.db, test_query):
            QMessageBox.information(
                self.dlg, plugin_name,
                'Connected sucessfully.', QMessageBox.Ok)
            self.dlg.load_server_structure()
        else:
            QMessageBox.warning(
                self.dlg, plugin_name,
                'Failed to connect.', QMessageBox.Ok)
