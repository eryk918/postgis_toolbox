# -*- coding: utf-8 -*-

from plugins.db_manager.dlg_query_builder import QueryBuilderDlg
from qgis.PyQt.QtCore import QCoreApplication


class CustomQueryBuilder(QueryBuilderDlg):
    def __init__(self, main_class, db, parent=None, reset=False):
        super(CustomQueryBuilder, self).__init__(
            main_class.iface, db, parent, reset)
        self.main_class = main_class
        self.retranslateUi(self.ui)

    def retranslateUi(self, CustomQueryBuilder):
        _translate = QCoreApplication.translate
        self.ui.label.setText(_translate("QueryBuilderDlg", "Kolumny"))
        self.ui.label_2.setText(_translate("QueryBuilderDlg", "Tabele"))
        self.ui.tables.setItemText(0, _translate("QueryBuilderDlg",
                                                 "Tabele"))
        self.ui.columns.setItemText(0, _translate("QueryBuilderDlg",
                                                  "Kolumny"))
        self.ui.columns_2.setItemText(0, _translate("QueryBuilderDlg",
                                                    "Kolumny"))
