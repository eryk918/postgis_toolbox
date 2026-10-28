# -*- coding: utf-8 -*-
import os
from typing import Dict, List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QTableWidgetItem, QTreeWidgetItem, \
    QHeaderView

from ..utils.registry_utils import TableInfo, kind_key
from ...utils import repair_dialog, tr, Qt

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'table_registry_dialog.ui'))

KIND_LABELS = {
    'vector': 'Vector',
    'raster': 'Raster',
    'r': 'Table',
    'p': 'Table',
    'v': 'View',
    'm': 'Materialized view',
    'f': 'Foreign table',
}

DETAIL_LABELS = {
    'rows': 'Estimated rows',
    'primary_key': 'Primary key',
    'geometry': 'Geometry columns',
    'raster': 'Raster',
    'overviews': 'Overviews',
    'columns': 'Columns',
    'indexes': 'Indexes',
}

RASTER_DETAIL_LABELS = {
    'bands': 'Bands',
    'scale': 'Pixel size',
    'block_size': 'Block size',
}


class TableRegistryDialog(QDialog, FORM_CLASS):
    def __init__(self, registry, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.registry = registry
        repair_dialog(self, 'table_registry.svg')
        self.setWindowFlags(Qt.Window)
        self.filter_lineedit.setShowSearchIcon(True)
        self.filter_lineedit.setPlaceholderText(tr('Filter tables'))
        self.tables_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.details_tree.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.refresh_btn.clicked.connect(self.registry.refresh)
        self.add_layer_btn.clicked.connect(self.registry.add_layer)
        self.rename_btn.clicked.connect(self.registry.rename_table)
        self.delete_btn.clicked.connect(self.registry.delete_table)
        self.filter_lineedit.valueChanged.connect(self.apply_filter)
        self.tables_table.itemSelectionChanged.connect(
            self.selection_changed)
        self.tables_table.itemDoubleClicked.connect(
            lambda item: self.registry.add_layer())
        self.selection_changed()

    def fill_tables(self, tables: List[TableInfo]) -> None:
        self.tables_table.setSortingEnabled(False)
        self.tables_table.setRowCount(0)
        self.tables_table.setRowCount(len(tables))
        for row, info in enumerate(tables):
            values = [info.schema, info.name,
                      tr(KIND_LABELS[kind_key(info)]),
                      self.geometry_label(info), self.srid_label(info)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, info)
                self.tables_table.setItem(row, column, item)
        self.tables_table.setSortingEnabled(True)
        self.tables_table.sortItems(0)
        self.apply_filter(self.filter_lineedit.value())
        self.details_tree.clear()
        self.selection_changed()

    def geometry_label(self, info: TableInfo) -> str:
        if info.is_raster():
            return tr('{0} band(s)').format(info.num_bands)
        if info.is_vector():
            return ', '.join(sorted({geometry_type for _, geometry_type, _, _
                                     in info.geometry_columns}))
        return ''

    def srid_label(self, info: TableInfo) -> str:
        if info.is_raster():
            return str(info.raster_srid)
        if info.is_vector():
            return ', '.join(sorted({str(srid) for _, _, srid, _
                                     in info.geometry_columns}))
        return ''

    def apply_filter(self, text: str) -> None:
        pattern = (text or '').strip().lower()
        for row in range(self.tables_table.rowCount()):
            schema = self.tables_table.item(row, 0).text().lower()
            name = self.tables_table.item(row, 1).text().lower()
            visible = not pattern or pattern in schema or pattern in name \
                or pattern in f'{schema}.{name}'
            self.tables_table.setRowHidden(row, not visible)

    def selected_table(self) -> Optional[TableInfo]:
        rows = self.tables_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.tables_table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def selection_changed(self) -> None:
        info = self.selected_table()
        selected = info is not None
        self.add_layer_btn.setEnabled(selected)
        self.rename_btn.setEnabled(selected)
        self.delete_btn.setEnabled(selected)
        self.details_tree.clear()
        if selected:
            self.registry.show_details(info)

    def fill_details(
            self, details: Dict[str, List[Tuple[str, str]]]) -> None:
        self.details_tree.clear()
        for key, rows in details.items():
            if not rows:
                continue
            section = QTreeWidgetItem([tr(DETAIL_LABELS[key]), ''])
            if len(rows) == 1 and not rows[0][0]:
                section.setText(1, rows[0][1])
            else:
                for name, value in rows:
                    label = tr(RASTER_DETAIL_LABELS[name]) \
                        if name in RASTER_DETAIL_LABELS else name
                    child = QTreeWidgetItem([label, value])
                    child.setToolTip(1, value)
                    section.addChild(child)
            self.details_tree.addTopLevelItem(section)
            section.setExpanded(key != 'indexes')
