# -*- coding: utf-8 -*-
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ...utils import repair_dialog, main_plugin_icon, fill_item, \
    get_all_tables_from_schema, make_query, \
    get_schema_name_list, unpack_nested_lists, create_progress_bar, Qt, os, \
    QApplication, get_active_db_info

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'db_manager_menu.ui'))


class DBManagerMenu_UI(QDialog, FORM_CLASS):
    def __init__(self, dbManager, parent=None):
        super(DBManagerMenu_UI, self).__init__(parent)
        self.setupUi(self)
        self.dbManager = dbManager
        repair_dialog(self)
        self.setWindowIcon(main_plugin_icon)
        self.setWindowFlags(Qt.Window)
        self.setWindowModality(Qt.NonModal)

    def setup_dialog(self) -> None:
        self.load_db_data_btn.clicked.connect(self.dbManager.connect_server)
        self.active_db_btn.clicked.connect(
            self.dbManager.select_operative_database)
        get_active_db_info(self.dbManager.db, self.active_db_label)

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
            0, txt='Loading server structure...')
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
            if schema_list:
                for schema_name in schema_list:
                    table_list = get_all_tables_from_schema(
                        new_db, schema_name)
                    table_list.sort()
                    if table_list:
                        schema_dict[schema_name] = list(table_list)
                if schema_dict:
                    db_dict[db_name] = schema_dict
            QApplication.processEvents()
        fill_item(table.invisibleRootItem(), db_dict)
        model.setHeaderData(0, 1, 'Databases')
        progress_bar.close()
        return db_dict
