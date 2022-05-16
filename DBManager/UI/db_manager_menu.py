# -*- coding: utf-8 -*-
import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from ...utils import repair_comboboxes, main_plugin_icon, fill_item, \
    get_all_tables_from_schema, get_schema_name_list_for_db

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'db_manager_menu.ui'))


class DBManagerMenu_UI(QDialog, FORM_CLASS):
    def __init__(self, dbManager, parent=None):
        super(DBManagerMenu_UI, self).__init__(parent)
        self.setupUi(self)
        self.dbManager = dbManager
        repair_comboboxes(self)
        self.setWindowIcon(main_plugin_icon)

    def setup_dialog(self) -> None:
        self.load_db_data_btn.clicked.connect(self.dbManager.connect_server)

    def run_dialog(self) -> None:
        self.show()
        self.exec_()

    def load_server_structure(self) -> None:
        db_list = [self.dbManager.db]
        table = self.db_obj_treeview
        table.clear()
        model = table.model()
        db_dict = {}
        # '''SELECT datname FROM pg_database WHERE datistemplate = false;'''
        for db in db_list:
            schema_dict = {}
            schema_list = get_schema_name_list_for_db(db)
            if schema_list:
                for schema_name in schema_list:
                    table_list = get_all_tables_from_schema(db, schema_name)
                    table_list.sort()
                    if table_list:
                        schema_dict[schema_name] = list(table_list)
                if schema_dict:
                    db_dict[db.databaseName()] = schema_dict
        fill_item(table.invisibleRootItem(), db_dict)
        model.setHeaderData(0, 1, 'Bazy danych')
