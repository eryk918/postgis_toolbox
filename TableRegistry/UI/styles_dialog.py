# -*- coding: utf-8 -*-
import os
from typing import List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QHeaderView, QTableWidgetItem, \
    QWidget
from qgis.core import QgsMapLayer, QgsProject

from ...utils import repair_dialog, tr, Qt

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'styles_dialog.ui'))

STYLE_ID_ROLE = Qt.UserRole
GEOMETRY_COLUMN_ROLE = Qt.UserRole + 1


class StylesDialog(QDialog, FORM_CLASS):
    apply_requested = pyqtSignal(int)
    save_requested = pyqtSignal()
    default_requested = pyqtSignal(int, str)
    rename_requested = pyqtSignal(int, str)
    delete_requested = pyqtSignal(int, str)

    def __init__(self, object_name: str, layers: List[QgsMapLayer],
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'table_registry.svg')
        self.object_name_label.setText(object_name)
        self.styles_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.styles_table.horizontalHeader().setStretchLastSection(True)
        self.layer_cbbx.addItem(tr('No layer selected'), None)
        for layer in layers:
            self.layer_cbbx.addItem(layer.name(), layer.id())
        if layers:
            self.layer_cbbx.setCurrentIndex(1)
        self.layer_cbbx.currentIndexChanged.connect(self.selection_changed)
        self.styles_table.itemSelectionChanged.connect(
            self.selection_changed)
        self.styles_table.itemDoubleClicked.connect(
            lambda item: self.request_apply())
        self.apply_btn.clicked.connect(self.request_apply)
        self.save_btn.clicked.connect(self.save_requested)
        self.default_btn.clicked.connect(self.request_default)
        self.rename_btn.clicked.connect(self.request_rename)
        self.delete_btn.clicked.connect(self.request_delete)
        self.selection_changed()

    def fill(self, styles: List[Tuple]) -> None:
        self.styles_table.setRowCount(0)
        self.styles_table.setRowCount(len(styles))
        for row, style in enumerate(styles):
            style_id, name, column, default, owner, updated, description, \
                _ = style
            values = [name, tr('Yes') if default else '', column or '',
                      owner or '', updated or '', description or '']
            for position, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if position == 0:
                    item.setData(STYLE_ID_ROLE, style_id)
                    item.setData(GEOMETRY_COLUMN_ROLE, column or '')
                self.styles_table.setItem(row, position, item)
        self.selection_changed()

    def selected_style(self) -> Optional[Tuple[int, str, str]]:
        rows = self.styles_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.styles_table.item(rows[0].row(), 0)
        return item.data(STYLE_ID_ROLE), item.text(), \
            item.data(GEOMETRY_COLUMN_ROLE)

    def selected_layer(self) -> Optional[QgsMapLayer]:
        layer_id = self.layer_cbbx.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def selection_changed(self) -> None:
        style = self.selected_style() is not None
        layer = self.selected_layer() is not None
        self.apply_btn.setEnabled(style and layer)
        self.save_btn.setEnabled(layer)
        self.default_btn.setEnabled(style)
        self.rename_btn.setEnabled(style)
        self.delete_btn.setEnabled(style)

    def request_apply(self) -> None:
        style = self.selected_style()
        if style is not None and self.selected_layer() is not None:
            self.apply_requested.emit(style[0])

    def request_default(self) -> None:
        style = self.selected_style()
        if style is not None:
            self.default_requested.emit(style[0], style[2])

    def request_rename(self) -> None:
        style = self.selected_style()
        if style is not None:
            self.rename_requested.emit(style[0], style[1])

    def request_delete(self) -> None:
        style = self.selected_style()
        if style is not None:
            self.delete_requested.emit(style[0], style[1])
