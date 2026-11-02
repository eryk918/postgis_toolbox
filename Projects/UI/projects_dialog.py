# -*- coding: utf-8 -*-
import os
from typing import List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QHeaderView, QTableWidgetItem

from ...utils import repair_dialog, tr, Qt

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'projects_dialog.ui'))


class ProjectsDialog(QDialog, FORM_CLASS):
    def __init__(self, projects, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.projects = projects
        repair_dialog(self, 'db_projects.svg')
        self.setWindowFlags(Qt.Window)
        self.projects_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.projects_table.horizontalHeader().setStretchLastSection(True)
        self.refresh_btn.clicked.connect(self.projects.refresh)
        self.schema_cbbx.currentIndexChanged.connect(
            lambda index: self.projects.load_projects())
        self.open_btn.clicked.connect(self.projects.open_project)
        self.save_btn.clicked.connect(self.projects.save_project)
        self.delete_btn.clicked.connect(self.projects.delete_project)
        self.projects_table.itemSelectionChanged.connect(
            self.selection_changed)
        self.projects_table.itemDoubleClicked.connect(
            lambda item: self.projects.open_project())
        self.selection_changed()

    def fill_schemas(self, schemas: List[str], current: str) -> None:
        self.schema_cbbx.blockSignals(True)
        self.schema_cbbx.clear()
        self.schema_cbbx.addItems(schemas)
        if current in schemas:
            self.schema_cbbx.setCurrentText(current)
        self.schema_cbbx.blockSignals(False)

    def schema(self) -> str:
        return self.schema_cbbx.currentText()

    def fill(self, projects: List[Tuple[str, str]]) -> None:
        self.projects_table.setSortingEnabled(False)
        self.projects_table.setRowCount(0)
        self.projects_table.setRowCount(len(projects))
        for row, values in enumerate(projects):
            for column, value in enumerate(values):
                self.projects_table.setItem(
                    row, column, QTableWidgetItem(value))
        self.projects_table.setSortingEnabled(True)
        self.projects_table.sortItems(0)
        self.info_label.setText(
            tr('No projects are stored in this schema yet. '
               '"Save current project" creates the qgis_projects table.')
            if not projects else '')
        self.selection_changed()

    def selected_project(self) -> Optional[str]:
        rows = self.projects_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.projects_table.item(rows[0].row(), 0).text()

    def select_project(self, name: str) -> None:
        for row in range(self.projects_table.rowCount()):
            if self.projects_table.item(row, 0).text() == name:
                self.projects_table.selectRow(row)
                return

    def selection_changed(self) -> None:
        selected = self.selected_project() is not None
        self.open_btn.setEnabled(selected)
        self.delete_btn.setEnabled(selected)
