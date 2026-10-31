# -*- coding: utf-8 -*-
import os
from typing import List, Set

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QWidget

from ..utils.admin_utils import TABLE_PRIVILEGES
from ...utils import repair_dialog

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'privileges_dialog.ui'))


class PrivilegesDialog(QDialog, FORM_CLASS):
    role_changed = pyqtSignal(str)
    apply_requested = pyqtSignal()

    def __init__(self, object_name: str, roles: List[str], owner: str,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'table_registry.svg')
        self.object_name_label.setText(object_name)
        self.owner_cbbx.addItems(roles)
        self.owner_cbbx.setCurrentText(owner)
        self.role_cbbx.addItems(['PUBLIC'] + roles)
        self.checkboxes = {
            privilege: getattr(self, f'{privilege.lower()}_chkbox')
            for privilege in TABLE_PRIVILEGES}
        self.all_btn.clicked.connect(lambda: self.set_privileges(
            set(TABLE_PRIVILEGES)))
        self.none_btn.clicked.connect(lambda: self.set_privileges(set()))
        self.role_cbbx.currentTextChanged.connect(self.role_changed)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(
            self.apply_requested)

    def selected_role(self) -> str:
        return self.role_cbbx.currentText()

    def selected_owner(self) -> str:
        return self.owner_cbbx.currentText()

    def set_privileges(self, privileges: Set[str]) -> None:
        for privilege, checkbox in self.checkboxes.items():
            checkbox.setChecked(privilege in privileges)

    def checked_privileges(self) -> Set[str]:
        return {privilege for privilege, checkbox in self.checkboxes.items()
                if checkbox.isChecked()}
