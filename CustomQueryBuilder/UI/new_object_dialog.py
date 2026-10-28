# -*- coding: utf-8 -*-
import os
from typing import List

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QWidget, QDialogButtonBox

from ...utils import repair_dialog, remove_unsupported_chars

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'new_object_dialog.ui'))


class NewObjectDialog(QDialog, FORM_CLASS):
    def __init__(self, title: str, name_label: str, schemas: List[str],
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'query_editor.svg')
        self.setWindowTitle(title)
        self.name_label.setText(f'{name_label}:')
        self.schema_cbbx.addItems(schemas)
        self.name_lineedit.textChanged.connect(self.update_ok_button)
        self.update_ok_button()

    def update_ok_button(self) -> None:
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.object_name()) and bool(self.schema_name()))

    def schema_name(self) -> str:
        return self.schema_cbbx.currentText()

    def object_name(self) -> str:
        return remove_unsupported_chars(self.name_lineedit.text().strip())
