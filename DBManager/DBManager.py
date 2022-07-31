# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtCore import QSettings

from .UI.db_manager_menu import DBManagerMenu_UI
from ..utils import project, iface, connection_key_names, \
    create_pg_connecton, make_query, plugin_name, test_query, QMessageBox, \
    create_progress_bar, QSqlDatabase, get_active_db_info


class DBManager:
    def __init__(self, parent):
        self.main = parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        self.actual_crs = project.crs().postgisSrid()
        self.plugin_dir = self.main.plugin_dir
        self.db = self.main.db

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
        progressbar = create_progress_bar(0, txt='Trying to connect...')
        progressbar.open()
        self.fetched_dbs = {}
        current_server = self.dlg.connection_cbbx.currentText()
        connection_parameters = self.connections_dict[current_server]
        self.dummydb = create_pg_connecton(connection_parameters)
        if self.dummydb.isValid() and self.dummydb.isOpen() and \
                make_query(self.dummydb, test_query):
            progressbar.close()
            self.fetched_dbs = self.dlg.load_server_structure()
        else:
            progressbar.close()
            QMessageBox.critical(
                self.dlg, plugin_name,
                'Failed to connect.', QMessageBox.Ok)

    def select_operative_database(self) -> None:
        self.db = None
        db_treeview = self.dlg.db_obj_treeview
        treeview_model = db_treeview.model()
        if treeview_model.rowCount() > 1:
            treeview_selection_model = db_treeview.selectionModel()
            selected_items = treeview_selection_model.selectedRows()
            if selected_items and selected_items[0]:
                db_name = selected_items[0]
                if db_name.parent().data():
                    while db_name.parent().data():
                        db_name = db_name.parent()
                db_name = db_name.data()
                if db_name in self.fetched_dbs.keys():
                    self.db = QSqlDatabase(self.dummydb)
                    self.db.setDatabaseName(db_name)
                    self.db.open()
                    if self.db.isOpen() and self.db.isValid() and \
                            make_query(self.db, test_query):
                        QMessageBox.information(
                            self.dlg, plugin_name,
                            f'Succesfully selected "{db_name}" '
                            f'as active database.',
                            QMessageBox.Ok)
                        self.main.db = self.db
                        get_active_db_info(
                            self.main.db, self.dlg.active_db_label)
                        get_active_db_info(
                            self.main.db, self.main.connection_label, True)
                    else:
                        QMessageBox.critical(
                            self.dlg, plugin_name,
                            'Selection failed - db user permission error.',
                            QMessageBox.Ok)
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                'Selection failed - '
                'connect to correct PostgreSQL server.',
                QMessageBox.Ok)
