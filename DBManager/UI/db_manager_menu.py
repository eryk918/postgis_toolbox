# -*- coding: utf-8 -*-
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ...utils import repair_dialog, fill_item, \
    get_all_tables_from_schema, make_query, \
    get_schema_name_list, unpack_nested_lists, create_progress_bar, Qt, os, \
    QApplication, get_active_db_info, tr

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'db_manager_menu.ui'))


class DBManagerMenu_UI(QDialog, FORM_CLASS):
    def __init__(self, dbManager, parent=None):
        super(DBManagerMenu_UI, self).__init__(parent)
        self.setupUi(self)
        self.dbManager = dbManager
        repair_dialog(self)
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
            True if tr('Not connected.') not in self.active_db_label.text()
            else False)
        self.add_conn_btn.clicked.connect(self.dbManager.add_connection)
        self.edit_conn_btn.clicked.connect(self.dbManager.edit_connection)
        self.remove_conn_btn.clicked.connect(self.dbManager.delete_connection)
        self.db_obj_treeview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.db_obj_treeview.customContextMenuRequested.connect(
            lambda: self.db_obj_treeview.selectionModel().clearSelection())

    def run_dialog(self) -> None:
        self.show()
        self.exec_()

    def load_server_structure(self) -> dict:
        if not self.dbManager.dummydb:
            return {}
        if not self.dbManager.dummydb.isOpen():
            self.dbManager.dummydb.open()
        if not self.dbManager.dummydb.isOpen():
            return {}
        table = self.db_obj_treeview
        table.clear()
        model = table.model()
        progress_bar = create_progress_bar(
            0,
            txt=tr('Loading server structure...'),
            title=tr('Fetching DB Info')
        )
        progress_bar.open()
        db_dict = {}
        db_list = unpack_nested_lists(make_query(
            self.dbManager.dummydb,
            '''SELECT datname 
               FROM pg_database 
               WHERE datistemplate = false;'''
        ))
        for db_name in db_list:
            schema_dict = {}
            schema_list, new_db = \
                get_schema_name_list(self.dbManager.dummydb, db_name)
            for schema_name in schema_list:
                table_list = get_all_tables_from_schema(
                    new_db, schema_name)
                table_list.sort()
                schema_dict[schema_name] = list(table_list)
            db_dict[db_name] = schema_dict
            QApplication.processEvents()
        fill_item(table.invisibleRootItem(), db_dict)
        model.setHeaderData(0, 1, tr('Databases'))
        progress_bar.close()
        return db_dict
