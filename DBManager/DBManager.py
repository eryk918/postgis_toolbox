# -*- coding: utf-8 -*-
import os
from typing import List

from qgis.PyQt.QtCore import QSettings

from .UI.db_manager_add import DBManagerAdd_UI
from .UI.db_manager_menu import DBManagerMenu_UI
from .db_utils.db_utils import get_postgis_version_extended_query, \
    get_postgis_version_query, create_schema, create_db, alter_schema, \
    alter_db, remove_schema, remove_db, get_dbs_query
from ..utils import project, iface, connection_key_names, \
    create_pg_connecton, make_query, plugin_name, test_query, QMessageBox, \
    create_progress_bar, QSqlDatabase, get_active_db_info, \
    universal_db_check, unpack_nested_lists, tr, main_plugin_icon, \
    get_schema_name_list


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
        self.dummydb = None
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

    def select_operative_database(self, silent: bool = False,
                                  db_name: str = False) -> None:
        self.db = None
        db_treeview = self.dlg.db_obj_treeview
        treeview_model = db_treeview.model()
        if treeview_model.rowCount() > 1 or db_name:
            if not db_name:
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
                if universal_db_check(self.db):
                    if not silent:
                        QMessageBox.information(
                            self.dlg, plugin_name,
                            f'Successfully selected "{db_name}" '
                            f'as active database.',
                            QMessageBox.Ok)
                    self.main.db = self.db
                    get_active_db_info(
                        self.main.db, self.dlg.active_db_label)
                    get_active_db_info(
                        self.main.db, self.main.connection_label, True)
                else:
                    if not silent:
                        QMessageBox.critical(
                            self.dlg, plugin_name,
                            'Selection failed - db user permission error.',
                            QMessageBox.Ok)
        else:
            if not silent:
                QMessageBox.critical(
                    self.dlg, plugin_name,
                    'Selection failed - '
                    'connect to correct PostgreSQL server or '
                    'no databases detected in server.',
                    QMessageBox.Ok)
        self.dlg.disconnect_btn.setEnabled(
            True if 'Not connected.' not in self.dlg.active_db_label.text()
            else False)

    def disconnect_db(self, silent: bool = False):
        if hasattr(self.main, 'db') and self.main.db:
            self.db = None
            self.main.db = None
            get_active_db_info(
                self.main.db, self.dlg.active_db_label)
            get_active_db_info(
                self.main.db, self.main.connection_label, True)
            self.dlg.disconnect_btn.setEnabled(False)
            if not silent:
                QMessageBox.information(
                    self.dlg, plugin_name,
                    tr('Successfully disconnected.'),
                    QMessageBox.Ok)
        else:
            if not silent:
                QMessageBox.information(
                    self.dlg, plugin_name,
                    tr('Already disconnected.'),
                    QMessageBox.Ok)

    def check_postgis_in_db(self) -> None:
        if universal_db_check(self.db):
            simple_pg_ver = unpack_nested_lists(make_query(
                self.db, get_postgis_version_query))
            extended_pg_ver = unpack_nested_lists(make_query(
                self.db, get_postgis_version_extended_query))
            if simple_pg_ver and extended_pg_ver:
                info_box = QMessageBox()
                info_box.setIcon(QMessageBox.Information)
                info_box.setText(tr(f"PostGIS extension was detected, "
                                    f"version is: {', '.join(simple_pg_ver)}"))
                info_box.setWindowTitle(plugin_name)
                info_box.setWindowIcon(main_plugin_icon)
                info_box.setDetailedText(extended_pg_ver[0])
                info_box.exec_()
            else:
                QMessageBox.critical(
                    self.dlg, plugin_name,
                    tr('No PostGIS extension was '
                       'detected in the selected database!'),
                    QMessageBox.Ok)
        else:
            if 'Not connected.' in self.dlg.active_db_label.text():
                QMessageBox.critical(
                    self.dlg, plugin_name,
                    tr('PostGIS version check failed!\n'
                       'Connect to correct PostgreSQL server and try again.'),
                    QMessageBox.Ok)
            else:
                QMessageBox.critical(
                    self.dlg, plugin_name,
                    tr('No PostGIS extension was '
                       'detected in the selected database!'),
                    QMessageBox.Ok)

    def add_db_object(self) -> None:
        db = self.dummydb if universal_db_check(self.dummydb) else self.db
        db_info_list = []
        db_treeview = self.dlg.db_obj_treeview
        treeview_selection_model = db_treeview.selectionModel()
        selected_items = treeview_selection_model.selectedRows()
        if selected_items and selected_items[0]:
            db_name = selected_items[0]
            db_info_list.append(db_name.data())
            if db_name.parent().data():
                while db_name.parent().data():
                    db_name = db_name.parent()
                    db_info_list.append(db_name.data())
        if universal_db_check(db):
            if len(db_info_list) > 0:
                add_dialog = DBManagerAdd_UI(self)
                add_dialog.setup_dialog(
                    tr('Enter a name for the new schema'),
                    tr('Schema name...')
                )
                add_dialog.run_dialog(
                    self.save_schema, self.get_schema_list(db_info_list[-1]))
            elif not db_info_list:
                add_dialog = DBManagerAdd_UI(self)
                add_dialog.setup_dialog(
                    tr('Enter a name for the new database'),
                    tr('Database name...')
                )
                add_dialog.run_dialog(self.save_database, self.get_db_list())

    def edit_db_object(self) -> None:
        db = self.dummydb if universal_db_check(self.dummydb) else self.db
        db_info_list = []
        db_treeview = self.dlg.db_obj_treeview
        treeview_selection_model = db_treeview.selectionModel()
        selected_items = treeview_selection_model.selectedRows()
        if selected_items and selected_items[0]:
            db_name = selected_items[0]
            db_info_list.append(db_name.data())
            if db_name.parent().data():
                while db_name.parent().data():
                    db_name = db_name.parent()
                    db_info_list.append(db_name.data())
        if universal_db_check(db) and db_info_list:
            self.old_name = db_info_list[0]
            if len(db_info_list) == 2:
                add_dialog = DBManagerAdd_UI(self)
                add_dialog.setup_dialog(
                    tr('Enter a name for schema'),
                    tr('Schema name...')
                )
                add_dialog.run_dialog(
                    self.rename_schema, self.get_schema_list(db_info_list[-1]))
            elif len(db_info_list) == 1:
                add_dialog = DBManagerAdd_UI(self)
                add_dialog.setup_dialog(
                    tr('Enter a name for database'),
                    tr('Database name...')
                )
                db_list = self.get_db_list()
                response = QMessageBox.warning(
                    self.dlg, plugin_name,
                    'Rename database disconnects from her all active users.\n'
                    'Do you want to continue?',
                    QMessageBox.Yes, QMessageBox.No)
                if response == QMessageBox.Yes:
                    add_dialog.run_dialog(self.rename_database, db_list)

    def remove_db_object(self) -> None:
        db = self.dummydb if universal_db_check(self.dummydb) else self.db
        db_info_list = []
        db_treeview = self.dlg.db_obj_treeview
        treeview_selection_model = db_treeview.selectionModel()
        selected_items = treeview_selection_model.selectedRows()
        if selected_items and selected_items[0]:
            db_name = selected_items[0]
            db_info_list.append(db_name.data())
            if db_name.parent().data():
                while db_name.parent().data():
                    db_name = db_name.parent()
                    db_info_list.append(db_name.data())
        if universal_db_check(db) and db_info_list:
            self.old_name = db_info_list[0]
            if len(db_info_list) == 2:
                response = QMessageBox.warning(
                    self.dlg, plugin_name,
                    f'Deletion of the "{self.old_name}" schema is '
                    f'irreversible!\nDo you want to continue?',
                    QMessageBox.Yes, QMessageBox.No)
                if response == QMessageBox.Yes:
                    self.remove_schema()
            elif len(db_info_list) == 1:
                response = QMessageBox.warning(
                    self.dlg, plugin_name,
                    f'Deletion of the "{self.old_name}" database is '
                    f'irreversible!\nDo you want to continue?',
                    QMessageBox.Yes, QMessageBox.No)
                if response == QMessageBox.Yes:
                    self.remove_database()

    def get_db_list(self) -> List[str]:
        return unpack_nested_lists(make_query(
            self.dummydb,
            get_dbs_query
        ))

    def get_schema_list(self, db_name: str) -> List[str]:
        schema_list, _ = get_schema_name_list(self.dummydb, db_name)
        return schema_list

    def save_database(self, db_name: str) -> None:
        create_db(self.dummydb, db_name)
        if db_name in self.get_db_list():
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(f'Successfully added "{db_name}" '
                   f'and set as active database.'),
                QMessageBox.Ok)
            self.connect_server()
            self.select_operative_database(True, db_name)
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while adding a database!'),
                QMessageBox.Ok)

    def save_schema(self, schema_name: str) -> None:
        self.select_operative_database(True)
        create_schema(self.db, schema_name)
        if schema_name in self.get_schema_list(self.db.databaseName()):
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(f'Successfully added "{schema_name}" and '
                   f'set as active schema.'),
                QMessageBox.Ok)
            self.connect_server()
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while adding a schema!'),
                QMessageBox.Ok)

    def rename_database(self, db_name: str) -> None:
        alter_db(self.dummydb, self.old_name, db_name)
        if db_name in self.get_db_list():
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(f'Successfully renamed "{self.old_name}" to "{db_name}" '
                   f'and set as active database.'),
                QMessageBox.Ok)
            self.connect_server()
            self.select_operative_database(True, db_name)
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while renaming the database!'),
                QMessageBox.Ok)

    def rename_schema(self, schema_name: str) -> None:
        self.select_operative_database(True)
        alter_schema(self.db, self.old_name, schema_name)
        if schema_name in self.get_schema_list(self.db.databaseName()):
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(
                    f'Successfully renamed "{self.old_name}" to "{schema_name}" '
                    f'and set as active schema.'),
                QMessageBox.Ok)
            self.connect_server()
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while renaming the schema!'),
                QMessageBox.Ok)

    def remove_database(self) -> None:
        remove_db(self.dummydb, self.old_name)
        if self.old_name not in self.get_db_list():
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(f'Successfully removed "{self.old_name}" database.'),
                QMessageBox.Ok)
            self.connect_server()
            if hasattr(self, 'db') and self.db and \
                    self.db.databaseName() == self.old_name:
                self.disconnect_db(True)
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while removing the database!'),
                QMessageBox.Ok)

    def remove_schema(self) -> None:
        self.select_operative_database(True)
        remove_schema(self.db, self.old_name)
        if self.old_name not in self.get_schema_list(self.db.databaseName()):
            QMessageBox.information(
                self.dlg, plugin_name,
                tr(f'Successfully removed "{self.old_name}" schema.'),
                QMessageBox.Ok)
            self.connect_server()
        else:
            QMessageBox.critical(
                self.dlg, plugin_name,
                tr('An error occurred while removing the schema!'),
                QMessageBox.Ok)
