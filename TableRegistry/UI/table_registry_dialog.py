# -*- coding: utf-8 -*-
import os
from typing import Dict, List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QTableWidgetItem, QTreeWidgetItem, \
    QHeaderView, QMenu

from .registry_view import LAYER_URI_ROLE
from ..utils.admin_utils import GEOMETRY_TYPES, OVERVIEW_LIMITS, TILE_SIZES
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
    'exact_rows': 'Row count',
    'size': 'Size on disk',
    'maintenance': 'Maintenance',
    'owner': 'Owner',
    'privileges': 'Privileges',
    'primary_key': 'Primary key',
    'geometry': 'Geometry columns',
    'raster': 'Raster',
    'overviews': 'Overviews',
    'columns': 'Columns',
    'indexes': 'Indexes',
    'invalid': 'Invalid geometries',
}

SUB_LABELS = {
    'bands': 'Bands',
    'scale': 'Pixel size',
    'block_size': 'Block size',
    'last_vacuum': 'Last vacuum',
    'last_analyze': 'Last analyze',
    'dead_rows': 'Dead rows',
}

COLLAPSED_SECTIONS = ('indexes', 'columns', 'privileges')


class TableRegistryDialog(QDialog, FORM_CLASS):
    def __init__(self, registry, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self.registry = registry
        self.busy = False
        repair_dialog(self, 'table_registry.svg')
        self.progress_label.hide()
        self.progress_bar.hide()
        self.setWindowFlags(Qt.Window)
        self.filter_lineedit.setShowSearchIcon(True)
        self.filter_lineedit.setPlaceholderText(tr('Filter tables'))
        self.tables_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.details_tree.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.tools_menu = QMenu(self)
        self.tools_btn.setMenu(self.tools_menu)
        self.refresh_btn.clicked.connect(self.registry.refresh)
        self.add_layer_btn.clicked.connect(self.registry.add_layer)
        self.export_btn.clicked.connect(self.registry.export_table)
        self.rename_btn.clicked.connect(self.registry.rename_table)
        self.delete_btn.clicked.connect(self.registry.delete_table)
        self.privileges_btn.clicked.connect(self.registry.edit_privileges)
        self.filter_lineedit.valueChanged.connect(self.apply_filter)
        self.tables_table.itemSelectionChanged.connect(
            self.selection_changed)
        self.tables_table.itemDoubleClicked.connect(
            lambda item: self.registry.add_layer())
        self.tables_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tables_table.customContextMenuRequested.connect(
            self.show_context_menu)
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
                    item.setData(LAYER_URI_ROLE,
                                 self.registry.layer_uris(info))
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
        for button in (self.add_layer_btn, self.export_btn, self.rename_btn,
                       self.delete_btn, self.privileges_btn, self.tools_btn):
            button.setEnabled(selected and not self.busy)
        self.details_tree.clear()
        if selected:
            self.registry.show_details(info)
            self.tools_menu.clear()
            self.fill_tools_menu(self.tools_menu, info)

    def set_busy(self, busy: bool, text: str = '') -> None:
        self.busy = busy
        self.progress_label.setText(text)
        self.progress_label.setVisible(busy)
        self.progress_bar.setVisible(busy)
        self.set_progress(None)
        self.refresh_btn.setEnabled(not busy)
        self.selection_changed()

    def set_progress(self, value: Optional[int]) -> None:
        if value is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)

    def show_context_menu(self, pos) -> None:
        item = self.tables_table.itemAt(pos)
        if item is None or self.busy:
            return
        self.tables_table.selectRow(item.row())
        info = self.selected_table()
        if info is None:
            return
        registry = self.registry
        menu = QMenu(self)
        menu.addAction(tr('Add to project'), registry.add_layer)
        menu.addAction(tr('Export...'), registry.export_table)
        menu.addSeparator()
        menu.addAction(tr('Rename...'), registry.rename_table)
        menu.addAction(tr('Delete'), registry.delete_table)
        menu.addAction(tr('Privileges...'), registry.edit_privileges)
        menu.addSeparator()
        self.fill_tools_menu(menu, info)
        menu.exec(self.tables_table.viewport().mapToGlobal(pos))

    def fill_tools_menu(self, menu: QMenu, info: TableInfo) -> None:
        registry = self.registry
        menu.addAction(tr('Count rows'), registry.count_rows)
        if info.relkind in ('r', 'p', 'm'):
            menu.addAction(tr('Vacuum and analyze'), registry.vacuum)
        if info.relkind == 'm':
            menu.addAction(tr('Refresh materialized view'),
                           registry.refresh_view)
        if info.relkind in ('r', 'p'):
            menu.addAction(tr('Add primary key'), registry.add_primary_key)
        if info.is_vector() or info.is_raster():
            menu.addAction(tr('Create spatial index'),
                           registry.create_spatial_index)
        menu.addSeparator()
        menu.addAction(tr('Move or rename...'), registry.move_table)
        menu.addAction(tr('Copy to schema...'), registry.copy_table)
        if info.is_vector():
            menu.addSeparator()
            menu.addAction(tr('Check geometries'), registry.check_geometries)
            menu.addAction(tr('Update SRID...'), registry.update_srid)
            type_menu = menu.addMenu(tr('Force geometry type'))
            for geometry_type in GEOMETRY_TYPES:
                type_menu.addAction(
                    geometry_type,
                    lambda checked=False, value=geometry_type:
                    registry.force_geometry_type(value))
        if info.is_raster():
            menu.addSeparator()
            overview_menu = menu.addMenu(tr('Build overviews'))
            for limit in OVERVIEW_LIMITS:
                overview_menu.addAction(
                    tr('Up to 1:{0}').format(limit),
                    lambda checked=False, value=limit:
                    registry.build_overviews(value))
            menu.addAction(tr('Add raster constraints'),
                           registry.add_raster_constraints)
            tile_menu = menu.addMenu(tr('Retile into a new table'))
            for size in TILE_SIZES:
                tile_menu.addAction(
                    f'{size} x {size}',
                    lambda checked=False, value=size: registry.retile(value))

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
                    label = tr(SUB_LABELS[name]) if name in SUB_LABELS \
                        else name
                    child = QTreeWidgetItem([label, value])
                    child.setToolTip(1, value)
                    section.addChild(child)
            self.details_tree.addTopLevelItem(section)
            section.setExpanded(key not in COLLAPSED_SECTIONS)

    def add_detail_section(self, key: str,
                           rows: List[Tuple[str, str]]) -> None:
        for index in range(self.details_tree.topLevelItemCount()):
            item = self.details_tree.topLevelItem(index)
            if item.text(0) == tr(DETAIL_LABELS[key]):
                self.details_tree.takeTopLevelItem(index)
                break
        section = QTreeWidgetItem([tr(DETAIL_LABELS[key]), ''])
        if len(rows) == 1 and not rows[0][0]:
            section.setText(1, rows[0][1])
        else:
            for name, value in rows:
                child = QTreeWidgetItem([name, value])
                child.setToolTip(1, value)
                section.addChild(child)
        self.details_tree.insertTopLevelItem(0, section)
        section.setExpanded(True)
