# -*- coding: utf-8 -*-
from typing import List

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QRegExp
from qgis.PyQt.QtGui import QRegExpValidator
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ...utils import repair_dialog, os, plugin_name, tr, \
    remove_unsupported_chars

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'db_manager_add.ui'))


class DBManagerAdd_UI(QDialog, FORM_CLASS):
    def __init__(self, dbManager, parent=None):
        super(DBManagerAdd_UI, self).__init__(parent)
        self.setupUi(self)
        self.dbManager = dbManager
        repair_dialog(self)

    def setup_dialog(self, label_text: str, placeholder_text: str) -> None:
        self.object_label.setText(label_text)
        self.object_lineEdit.setPlaceholderText(placeholder_text)
        self.object_lineEdit.setValidator(
            QRegExpValidator(QRegExp('[A-Za-z0-9_-]{1,}')))
        self.buttonBox.accepted.connect(self.unsupported_text)

    def unsupported_text(self):
        input_text = remove_unsupported_chars(self.object_lineEdit.text())
        if not input_text:
            QMessageBox.critical(
                self, plugin_name,
                tr('Invalid name entered!\nTry again.'),
                QMessageBox.Ok)
        elif input_text in self.existing_obj_list:
            QMessageBox.critical(
                self, plugin_name,
                tr('The name entered is already in use!\nTry again.'),
                QMessageBox.Ok)
        else:
            self.accept()
            self.run_func(input_text)

    def run_dialog(self, func: callable, existing_list: List[str]) -> None:
        self.run_func = func
        self.existing_obj_list = existing_list
        self.exec()
