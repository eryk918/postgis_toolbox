# -*- coding: utf-8 -*-
import os
from typing import List, Optional

from qgis.PyQt.QtWidgets import QComboBox, QPushButton, QWidget
from qgis.core import QgsProviderRegistry
from qgis.gui import QgsGui

from .UI.db_manager_add import DBManagerAdd_UI
from .UI.db_manager_menu import DBManagerMenu_UI
from .UI.sessions_dialog import SessionsDialog
from .db_utils.db_utils import get_postgis_version_extended_query, \
    get_postgis_version_query, create_schema, create_db, alter_schema, \
    alter_db, remove_schema, remove_db, get_dbs_query, sessions_query, \
    cancel_backend_query, terminate_backend_query
from ..utils import project, iface, make_query, ask_question, \
    show_error, show_info, create_progress_bar, get_active_db_info, \
    check_connection, tr, get_schema_names, \
    delete_item_from_combo, get_connection_names, create_connection, \
    connection_for_database, postgres_metadata, read_setting, Qt


class DBManager:
    def __init__(self, parent, dialog_parent: Optional[QWidget] = None):
        self.main = parent
        self.dialog_parent = dialog_parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        self.actual_crs = project.crs().postgisSrid()
        self.plugin_dir = self.main.plugin_dir
        self.db = self.main.db
        self.server_connection = None
        self.fetched_dbs = {}
        self.source_widget = None
        self.sessions_dialog = None

    def run(self) -> None:
        self.source_widget = None
        self.sessions_dialog = None
        self.dlg = DBManagerMenu_UI(self, self.dialog_parent)
        self.dlg.setup_dialog()
        self.fetch_connections()
        self.dlg.run_dialog()

    def fetch_connections(self, selected_name: str = None) -> None:
        self.dlg.connection_cbbx.clear()
        self.dlg.connection_cbbx.addItems(get_connection_names())
        current_name = selected_name or self.main.connection_name
        if current_name:
            index = self.dlg.connection_cbbx.findText(current_name)
            if index != -1:
                self.dlg.connection_cbbx.setCurrentIndex(index)

    def connection_widget(self) -> Optional[QWidget]:
        if self.source_widget is None:
            provider = QgsGui.sourceSelectProviderRegistry().providerByName(
                'postgres')
            if provider is None:
                return None
            self.source_widget = provider.createDataSourceWidget(
                self.dlg, Qt.Widget, QgsProviderRegistry.WidgetMode.Embedded)
            self.source_widget.hide()
            self.source_widget.connectionsChanged.connect(
                self.connections_changed)
        return self.source_widget

    def click_connection_button(self, button_name: str,
                                connection_name: str = '') -> None:
        widget = self.connection_widget()
        combo = widget.findChild(QComboBox, 'cmbConnections') \
            if widget is not None else None
        button = widget.findChild(QPushButton, button_name) \
            if widget is not None else None
        if combo is None or button is None:
            show_error(
                self.dlg,
                tr('The QGIS PostgreSQL connection dialog is not available.'))
            return
        widget.refresh()
        if connection_name:
            combo.setCurrentIndex(combo.findText(connection_name))
        button.click()

    def connections_changed(self) -> None:
        combo = self.source_widget.findChild(QComboBox, 'cmbConnections')
        self.fetch_connections(combo.currentText() if combo else None)

    def add_connection(self) -> None:
        self.click_connection_button('btnNew')

    def edit_connection(self) -> None:
        connection_name = self.dlg.connection_cbbx.currentText()
        if connection_name:
            self.click_connection_button('btnEdit', connection_name)

    def delete_connection(self) -> None:
        conn_name = self.dlg.connection_cbbx.currentText()
        if not conn_name:
            return
        question = ask_question(
            self.dlg,
            tr('Should this connection be deleted?'))
        if question:
            postgres_metadata().deleteConnection(conn_name)
            delete_item_from_combo(conn_name, self.dlg.connection_cbbx)

    def connect_server(self) -> None:
        progressbar = create_progress_bar(0, txt=tr('Trying to connect...'),
                                          parent=self.dlg)
        progressbar.open()
        self.fetched_dbs = {}
        current_server = self.dlg.connection_cbbx.currentText()
        self.server_connection = create_connection(current_server) \
            if current_server else None
        if check_connection(self.server_connection):
            progressbar.close()
            self.fetched_dbs = self.dlg.load_server_structure()
        else:
            progressbar.close()
            self.server_connection = None
            show_error(
                self.dlg,
                tr('Failed to connect.'))

    def reconnect_last(self) -> None:
        connection_name = read_setting('last/connection', '') or ''
        db_name = read_setting('last/database', '') or ''
        if not connection_name or not db_name:
            show_info(self.dlg, tr('No previous connection was recorded.'))
            return
        index = self.dlg.connection_cbbx.findText(connection_name)
        if index == -1:
            show_error(
                self.dlg,
                tr('Connection "{0}" no longer exists.').format(
                    connection_name))
            return
        self.dlg.connection_cbbx.setCurrentIndex(index)
        self.connect_server()
        if not self.server_connection:
            return
        if db_name not in self.fetched_dbs:
            show_error(
                self.dlg,
                tr('Database "{0}" was not found on the server.').format(
                    db_name))
            return
        self.dlg.select_database_item(db_name)
        self.select_operative_database(db_name=db_name)

    def selected_tree_path(self) -> List[str]:
        path = []
        selection = self.dlg.db_obj_treeview.selectionModel()
        selected_items = selection.selectedRows()
        if selected_items and selected_items[0]:
            index = selected_items[0]
            path.append(index.data())
            while index.parent().data():
                index = index.parent()
                path.append(index.data())
        return path

    def select_operative_database(
            self, silent: bool = False, db_name: str = None) -> None:
        self.db = None
        if not db_name:
            path = self.selected_tree_path()
            db_name = path[-1] if path else None
        if self.server_connection and db_name in self.fetched_dbs:
            self.db = connection_for_database(self.server_connection, db_name)
            if check_connection(self.db):
                if not silent:
                    show_info(
                        self.dlg,
                        tr('Successfully selected "{0}" as '
                           'active database.').format(db_name))
                self.main.set_active_db(
                    self.db, self.dlg.connection_cbbx.currentText())
                get_active_db_info(self.main.db, self.dlg.active_db_label)
            else:
                self.db = None
                if not silent:
                    show_error(
                        self.dlg,
                        tr('Selection failed - db user permission error.'))
        elif not silent:
            show_error(
                self.dlg,
                tr('Selection failed - '
                   'connect to correct PostgreSQL server or '
                   'no databases detected in server.'))
        self.dlg.disconnect_btn.setEnabled(
            tr('Not connected.') not in self.dlg.active_db_label.text())

    def sync_active_db(self) -> None:
        self.db = self.main.db
        get_active_db_info(self.main.db, self.dlg.active_db_label)
        self.dlg.disconnect_btn.setEnabled(self.main.db is not None)

    def disconnect_db(self, silent: bool = False):
        if self.main.db:
            self.main.disconnect_db()
        elif not silent:
            show_info(
                self.dlg,
                tr('Already disconnected.'))

    def check_postgis_in_db(self) -> None:
        if not check_connection(self.db):
            show_error(
                self.dlg,
                tr('PostGIS version check failed.\n'
                   'Connect to a PostgreSQL server with PostGIS and try '
                   'again.'))
            return
        simple_pg_ver = make_query(self.db, get_postgis_version_query)
        extended_pg_ver = make_query(
            self.db, get_postgis_version_extended_query)
        if simple_pg_ver and extended_pg_ver:
            show_info(
                self.dlg,
                tr('PostGIS extension was detected, version is: {0}').format(
                    simple_pg_ver[0][0]),
                str(extended_pg_ver[0][0]))
        else:
            show_error(
                self.dlg,
                tr('No PostGIS extension was '
                   'detected in the selected database.'))

    def sessions_connection(self):
        if check_connection(self.server_connection):
            return self.server_connection
        if check_connection(self.main.db):
            return self.main.db
        return None

    def show_sessions(self) -> None:
        if self.sessions_connection() is None:
            show_error(
                self.dlg,
                tr('Connect to a server first.'))
            return
        if self.sessions_dialog is None:
            self.sessions_dialog = SessionsDialog(self.dlg)
            self.sessions_dialog.refresh_requested.connect(
                self.refresh_sessions)
            self.sessions_dialog.cancel_requested.connect(self.cancel_query)
            self.sessions_dialog.terminate_requested.connect(
                self.terminate_session)
        self.refresh_sessions()
        self.sessions_dialog.show()
        self.sessions_dialog.raise_()
        self.sessions_dialog.activateWindow()

    def refresh_sessions(self) -> None:
        connection = self.sessions_connection()
        if connection is None or self.sessions_dialog is None:
            return
        rows = make_query(connection, sessions_query)
        if rows is None:
            self.sessions_dialog.auto_chkbox.setChecked(False)
            show_error(self.sessions_dialog,
                       tr('Reading the sessions failed.'))
            return
        self.sessions_dialog.fill([tuple(row) for row in rows])

    def cancel_query(self, pid: int) -> None:
        connection = self.sessions_connection()
        if connection is None:
            return
        if make_query(connection, cancel_backend_query(pid)) is None:
            show_error(self.sessions_dialog,
                       tr('Cancelling the query failed.'))
        self.refresh_sessions()

    def terminate_session(self, pid: int) -> None:
        connection = self.sessions_connection()
        if connection is None:
            return
        if not ask_question(
                self.sessions_dialog,
                tr('Terminate session {0}?\n'
                   'Its open transaction will be rolled back.').format(pid)):
            return
        if make_query(connection, terminate_backend_query(pid)) is None:
            show_error(self.sessions_dialog,
                       tr('Terminating the session failed.'))
        self.refresh_sessions()

    def add_db_object(self) -> None:
        path = self.selected_tree_path()
        if not check_connection(self.server_connection):
            return
        add_dialog = DBManagerAdd_UI(self)
        if path:
            add_dialog.setup_dialog(
                tr('Enter a name for the new schema'),
                tr('Schema name...')
            )
            add_dialog.run_dialog(
                self.save_schema, self.get_schema_list(path[-1]))
        else:
            add_dialog.setup_dialog(
                tr('Enter a name for the new database'),
                tr('Database name...')
            )
            add_dialog.run_dialog(self.save_database, self.get_db_list())

    def edit_db_object(self) -> None:
        path = self.selected_tree_path()
        if not check_connection(self.server_connection) or not path:
            return
        self.old_name = path[0]
        add_dialog = DBManagerAdd_UI(self)
        if len(path) == 2:
            add_dialog.setup_dialog(
                tr('Enter a name for schema'),
                tr('Schema name...')
            )
            add_dialog.run_dialog(
                self.rename_schema, self.get_schema_list(path[-1]))
        elif len(path) == 1:
            add_dialog.setup_dialog(
                tr('Enter a name for database'),
                tr('Database name...')
            )
            response = ask_question(
                self.dlg,
                tr('Rename database disconnects from her all active users.\n'
                   'Do you want to continue?'))
            if response:
                add_dialog.run_dialog(self.rename_database, self.get_db_list())

    def remove_db_object(self) -> None:
        path = self.selected_tree_path()
        if not check_connection(self.server_connection) or not path:
            return
        self.old_name = path[0]
        if len(path) == 2:
            response = ask_question(
                self.dlg,
                tr('Deletion of the "%s" schema is irreversible.\n'
                   'Do you want to continue?') % self.old_name)
            if response:
                self.remove_schema()
        elif len(path) == 1:
            response = ask_question(
                self.dlg,
                tr('Deletion of the "%s" database is irreversible.\n'
                   'Do you want to continue?') % self.old_name)
            if response:
                self.remove_database()

    def get_db_list(self) -> List[str]:
        rows = make_query(self.server_connection, get_dbs_query)
        return [row[0] for row in rows] if rows else []

    def get_schema_list(self, db_name: str) -> List[str]:
        return get_schema_names(
            connection_for_database(self.server_connection, db_name))

    def save_database(self, db_name: str) -> None:
        if create_db(self.server_connection, db_name) \
                and db_name in self.get_db_list():
            show_info(
                self.dlg,
                tr('Successfully added "%s".') % db_name)
            self.connect_server()
            self.select_operative_database(True, db_name)
        else:
            show_error(
                self.dlg,
                tr('An error occurred while adding a database.'))

    def save_schema(self, schema_name: str) -> None:
        self.select_operative_database(True)
        if self.db and create_schema(self.db, schema_name) \
                and schema_name in get_schema_names(self.db):
            show_info(
                self.dlg,
                tr('Successfully added "%s".') % schema_name)
            self.connect_server()
        else:
            show_error(
                self.dlg,
                tr('An error occurred while adding a schema.'))

    def rename_database(self, db_name: str) -> None:
        if self.main.db and self.main.connection_name and \
                self.old_name in self.fetched_dbs:
            self.disconnect_db(True)
        if alter_db(self.server_connection, self.old_name, db_name) \
                and db_name in self.get_db_list():
            show_info(
                self.dlg,
                tr('Successfully renamed "{0}" to "{1}".').format(
                    self.old_name, db_name))
            self.connect_server()
            self.select_operative_database(True, db_name)
        else:
            show_error(
                self.dlg,
                tr('An error occurred while renaming the database.'))

    def rename_schema(self, schema_name: str) -> None:
        self.select_operative_database(True)
        if self.db and alter_schema(self.db, self.old_name, schema_name) \
                and schema_name in get_schema_names(self.db):
            show_info(
                self.dlg,
                tr('Successfully renamed "{0}" to "{1}".').format(
                    self.old_name, schema_name))
            self.connect_server()
        else:
            show_error(
                self.dlg,
                tr('An error occurred while renaming the schema.'))

    def remove_database(self) -> None:
        self.disconnect_db(True)
        if remove_db(self.server_connection, self.old_name) \
                and self.old_name not in self.get_db_list():
            show_info(
                self.dlg,
                tr('Successfully removed "%s" database.') % self.old_name)
            self.connect_server()
        else:
            show_error(
                self.dlg,
                tr('An error occurred while removing the database.'))

    def remove_schema(self) -> None:
        self.select_operative_database(True)
        if self.db and remove_schema(self.db, self.old_name) \
                and self.old_name not in get_schema_names(self.db):
            show_info(
                self.dlg,
                tr('Successfully removed "%s" schema.') % self.old_name)
            self.connect_server()
        else:
            show_error(
                self.dlg,
                tr('An error occurred while removing the schema.'))
