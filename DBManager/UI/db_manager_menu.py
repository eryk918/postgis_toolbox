# -*- coding: utf-8 -*-
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ...utils import repair_dialog, fill_item, make_query, get_schema_tables, \
    create_progress_bar, Qt, os, QApplication, get_active_db_info, tr, \
    connection_for_database
from ..db_utils.db_utils import get_dbs_query

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

    def setup_dialog(self) -> None:
        self.load_db_data_btn.clicked.connect(self.dbManager.connect_server)
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
        rows = make_query(server_connection, get_dbs_query) or []
        for row in rows:
            db_name = row[0]
            db_dict[db_name] = get_schema_tables(
                connection_for_database(server_connection, db_name))
            QApplication.processEvents()
        fill_item(table.invisibleRootItem(), db_dict)
        model.setHeaderData(0, 1, tr('Databases'))
        progress_bar.close()
        return db_dict
