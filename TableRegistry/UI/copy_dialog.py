# -*- coding: utf-8 -*-
import os
from typing import List

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QWidget

from ...utils import repair_dialog, tr

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'copy_dialog.ui'))


class CopyDialog(QDialog, FORM_CLASS):
    connection_changed = pyqtSignal(str)
    database_changed = pyqtSignal(str, str)

    def __init__(self, object_name: str, connections: List[str],
                 default_name: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'table_registry.svg')
        self.object_name_label.setText(object_name)
        self.name_lineedit.setText(default_name)
        self.button_box.button(QDialogButtonBox.Ok).setText(tr('Copy'))
        self.button_box.accepted.connect(self.validate)
        self.connection_cbbx.currentTextChanged.connect(
            self.connection_changed)
        self.database_cbbx.currentTextChanged.connect(
            lambda database: self.database_changed.emit(
                self.connection_cbbx.currentText(), database))
        self.connection_cbbx.addItems(connections)

    def set_databases(self, databases: List[str], current: str = '') -> None:
        self.database_cbbx.clear()
        self.database_cbbx.addItems(databases)
        if current and current in databases:
            self.database_cbbx.setCurrentText(current)

    def set_schemas(self, schemas: List[str], current: str = '') -> None:
        self.schema_cbbx.clear()
        self.schema_cbbx.addItems(schemas)
        if current and current in schemas:
            self.schema_cbbx.setCurrentText(current)

    def connection_name(self) -> str:
        return self.connection_cbbx.currentText()

    def database(self) -> str:
        return self.database_cbbx.currentText()

    def schema(self) -> str:
        return self.schema_cbbx.currentText()

    def table_name(self) -> str:
        return self.name_lineedit.text().strip()

    def overwrite(self) -> bool:
        return self.overwrite_chkbox.isChecked()

    def spatial_index(self) -> bool:
        return self.index_chkbox.isChecked()

    def validate(self) -> None:
        if not self.connection_name() or not self.database() \
                or not self.schema() or not self.table_name():
            self.bar.pushWarning(
                tr('Copy'), tr('Fill in the required fields.'))
            return
        self.accept()
