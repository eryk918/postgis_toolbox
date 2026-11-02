# -*- coding: utf-8 -*-
import os
from typing import Dict, List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QHeaderView, QTreeWidgetItem, \
    QWidget

from ..utils.health_utils import HEALTH_CHECKS, FIXABLE_CHECKS
from ...utils import repair_dialog, tr, Qt

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'health_dialog.ui'))

CHECK_LABELS = {
    'no_primary_key': 'Tables without a primary key',
    'no_spatial_index': 'Spatial columns without an index',
    'dead_rows': 'Tables with many dead rows',
    'never_analyzed': 'Tables never analyzed',
    'unused_indexes': 'Unused indexes',
    'raster_no_constraints': 'Rasters without constraints',
}

CHECK_HINTS = {
    'no_primary_key': 'QGIS needs a primary key to edit a table',
    'no_spatial_index': 'Spatial queries scan the whole table',
    'dead_rows': 'Dead rows / live rows, VACUUM reclaims the space',
    'never_analyzed': 'Live rows, the planner has no statistics',
    'unused_indexes': 'Never scanned since the statistics were reset',
    'raster_no_constraints': 'raster_columns has no SRID, scale or bands',
}

CHECK_ROLE = Qt.UserRole
FINDING_ROLE = Qt.UserRole + 1


class HealthDialog(QDialog, FORM_CLASS):
    fix_requested = pyqtSignal(str, str, str)
    show_requested = pyqtSignal(str, str)
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'table_registry.svg')
        self.setWindowFlags(Qt.Window)
        self.findings_tree.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.findings_tree.itemSelectionChanged.connect(
            self.selection_changed)
        self.findings_tree.itemDoubleClicked.connect(
            lambda item, column: self.request_show())
        self.fix_btn.clicked.connect(self.request_fix)
        self.show_btn.clicked.connect(self.request_show)
        self.refresh_btn.clicked.connect(self.refresh_requested)
        self.set_busy(True)

    def set_busy(self, busy: bool) -> None:
        self.refresh_btn.setEnabled(not busy)
        if busy:
            self.summary_label.setText(tr('Checking the database...'))
        self.selection_changed()

    def fill(self, findings: Dict[str, List[Tuple[str, str, str]]]) -> None:
        self.findings_tree.clear()
        total = 0
        for check in HEALTH_CHECKS:
            rows = findings.get(check)
            if not rows:
                continue
            total += len(rows)
            section = QTreeWidgetItem(
                [f'{tr(CHECK_LABELS[check])} ({len(rows)})',
                 tr(CHECK_HINTS[check])])
            section.setData(0, CHECK_ROLE, check)
            section.setFlags(section.flags() & ~Qt.ItemIsSelectable)
            for schema, table, detail in rows:
                item = QTreeWidgetItem([f'{schema}.{table}', detail])
                item.setData(0, CHECK_ROLE, check)
                item.setData(0, FINDING_ROLE, (schema, table, detail))
                item.setToolTip(1, detail)
                section.addChild(item)
            self.findings_tree.addTopLevelItem(section)
            section.setExpanded(True)
        self.summary_label.setText(
            tr('No issues found.') if not total
            else tr('{0} issue(s) found.').format(total))
        self.set_busy(False)

    def selected_finding(self) -> Optional[Tuple[str, str, str, str]]:
        items = self.findings_tree.selectedItems()
        if not items or items[0].data(0, FINDING_ROLE) is None:
            return None
        schema, table, detail = items[0].data(0, FINDING_ROLE)
        return items[0].data(0, CHECK_ROLE), schema, table, detail

    def selection_changed(self) -> None:
        finding = self.selected_finding()
        enabled = finding is not None and self.refresh_btn.isEnabled()
        self.show_btn.setEnabled(enabled)
        self.fix_btn.setEnabled(enabled and finding[0] in FIXABLE_CHECKS)

    def request_fix(self) -> None:
        finding = self.selected_finding()
        if finding is not None and finding[0] in FIXABLE_CHECKS:
            self.fix_requested.emit(finding[0], finding[1], finding[2])

    def request_show(self) -> None:
        finding = self.selected_finding()
        if finding is not None:
            self.show_requested.emit(finding[1], finding[2])
