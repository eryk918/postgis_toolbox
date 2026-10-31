# -*- coding: utf-8 -*-
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ...utils import repair_dialog, fill_item, make_query, get_schema_tables, \
    create_progress_bar, Qt, os, QApplication, get_active_db_info, tr, \
    connection_for_database
from ..db_utils.db_utils import get_dbs_query, server_version_query, \
    database_info_query

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'db_manager_menu.ui'))


class DBManagerMenu_UI(QDialog, FORM_CLASS):
    def __init__(self, dbManager, parent=None):
        super(DBManagerMenu_UI, self).__init__(parent)
        self.setupUi(self)
        self.dbManager = dbManager
        repair_dialog(self, 'manage_dbs.svg')
        self.setWindowFlags(Qt.Window)
        self.setWindowModality(Qt.NonModal)
        self.server_info_label.clear()
        self.filter_lineedit.setShowSearchIcon(True)
        self.filter_lineedit.setPlaceholderText(
            tr('Filter databases, schemas and tables'))
        self.filter_lineedit.valueChanged.connect(self.apply_filter)

    def setup_dialog(self) -> None:
        self.load_db_data_btn.clicked.connect(self.dbManager.connect_server)
        self.last_db_btn.clicked.connect(self.dbManager.reconnect_last)
        self.active_db_btn.clicked.connect(
            self.dbManager.select_operative_database)
        self.verify_postgis_btn.clicked.connect(
            self.dbManager.check_postgis_in_db)
        self.add_obj_btn.clicked.connect(self.dbManager.add_db_object)
        self.edit_obj_btn.clicked.connect(self.dbManager.edit_db_object)
        self.remove_obj_btn.clicked.connect(self.dbManager.remove_db_object)
        self.disconnect_btn.clicked.connect(self.dbManager.disconnect_db)
        get_active_db_info(self.dbManager.db, self.active_db_label)
        self.disconnect_btn.setEnabled(
            tr('Not connected.') not in self.active_db_label.text())
        self.add_conn_btn.clicked.connect(self.dbManager.add_connection)
        self.edit_conn_btn.clicked.connect(self.dbManager.edit_connection)
        self.remove_conn_btn.clicked.connect(self.dbManager.delete_connection)
        self.db_obj_treeview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.db_obj_treeview.customContextMenuRequested.connect(
            lambda: self.db_obj_treeview.selectionModel().clearSelection())

    def run_dialog(self) -> None:
        self.show()
        self.exec()

    def apply_filter(self, text: str) -> None:
        pattern = (text or '').strip().lower()
        root = self.db_obj_treeview.invisibleRootItem()
        for index in range(root.childCount()):
            self.filter_item(root.child(index), pattern)

    def filter_item(self, item, pattern: str) -> bool:
        matched = not pattern or pattern in item.text(0).lower()
        child_visible = False
        for index in range(item.childCount()):
            child = item.child(index)
            if matched:
                self.filter_item(child, '')
                child_visible = True
            elif self.filter_item(child, pattern):
                child_visible = True
        visible = matched or child_visible
        item.setHidden(not visible)
        if pattern and child_visible and not matched:
            item.setExpanded(True)
        return visible

    def select_database_item(self, db_name: str) -> None:
        table = self.db_obj_treeview
        for index in range(table.topLevelItemCount()):
            item = table.topLevelItem(index)
            if item.text(0) == db_name:
                table.setCurrentItem(item)
                table.scrollToItem(item)
                return

    def load_server_structure(self) -> dict:
        server_connection = self.dbManager.server_connection
        if not server_connection:
            return {}
        table = self.db_obj_treeview
        table.clear()
        model = table.model()
        progress_bar = create_progress_bar(
            0,
            txt=tr('Loading server structure...'),
            title=tr('Fetching DB Info'),
            parent=self
        )
        progress_bar.open()
        db_dict = {}
        tooltips = {}
        rows = make_query(server_connection, get_dbs_query) or []
        for row in rows:
            db_name = row[0]
            db_connection = connection_for_database(server_connection, db_name)
            db_dict[db_name] = get_schema_tables(db_connection)
            tooltips[db_name] = self.database_tooltip(db_connection)
            QApplication.processEvents()
        fill_item(table.invisibleRootItem(), db_dict)
        for index in range(table.topLevelItemCount()):
            item = table.topLevelItem(index)
            item.setToolTip(0, tooltips.get(item.text(0), ''))
        model.setHeaderData(0, 1, tr('Databases'))
        self.show_server_info(server_connection, len(db_dict))
        self.apply_filter(self.filter_lineedit.value())
        progress_bar.close()
        return db_dict

    def database_tooltip(self, connection) -> str:
        rows = make_query(connection, database_info_query)
        if not rows:
            return ''
        size, extensions = rows[0]
        return '{0}: ~{1}\n{2}: {3}'.format(
            tr('Size'), size, tr('Extensions'), extensions or '-')

    def show_server_info(self, connection, database_count: int) -> None:
        rows = make_query(connection, server_version_query)
        version = rows[0][0] if rows else ''
        self.server_info_label.setText(
            tr('{0}, {1} database(s)').format(version, database_count))
