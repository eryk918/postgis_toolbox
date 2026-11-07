# -*- coding: utf-8 -*-
import os
from typing import List, Optional, Tuple

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QDialog, QHeaderView, QTableWidgetItem, \
    QWidget

from ...utils import repair_dialog, tr, Qt

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'sessions_dialog.ui'))

PID_ROLE = Qt.UserRole
OWN_ROLE = Qt.UserRole + 1
QUERY_ROLE = Qt.UserRole + 2
REFRESH_INTERVAL = 5000
QUERY_PREVIEW_LENGTH = 120


class SessionsDialog(QDialog, FORM_CLASS):
    refresh_requested = pyqtSignal()
    cancel_requested = pyqtSignal(int)
    terminate_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'manage_dbs.svg')
        self.setWindowFlags(Qt.Window)
        self.query_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.sessions_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.sessions_table.horizontalHeader().setStretchLastSection(True)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_INTERVAL)
        self.timer.timeout.connect(self.refresh_requested)
        self.auto_chkbox.toggled.connect(self.toggle_timer)
        self.active_chkbox.toggled.connect(self.apply_filter)
        self.refresh_btn.clicked.connect(self.refresh_requested)
        self.cancel_btn.clicked.connect(self.request_cancel)
        self.terminate_btn.clicked.connect(self.request_terminate)
        self.sessions_table.itemSelectionChanged.connect(
            self.selection_changed)
        self.selection_changed()

    def toggle_timer(self, enabled: bool) -> None:
        if enabled:
            self.timer.start()
        else:
            self.timer.stop()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        super().closeEvent(event)

    def fill(self, sessions: List[Tuple]) -> None:
        selected = self.selected_pid()
        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(0)
        self.sessions_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            pid, user, database, application, client, state, duration, \
                waiting, blocked_by, query, own = session
            if own:
                application = f'{application} ({tr("this QGIS")})'
            preview = ' '.join((query or '').split())
            if len(preview) > QUERY_PREVIEW_LENGTH:
                preview = preview[:QUERY_PREVIEW_LENGTH] + '...'
            values = [str(pid), user or '', database or '',
                      application or '', client or '', state or '',
                      duration or '', waiting or '', blocked_by or '',
                      preview]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.DisplayRole, int(pid))
                    item.setData(PID_ROLE, int(pid))
                    item.setData(OWN_ROLE, bool(own))
                    item.setData(QUERY_ROLE, query or '')
                self.sessions_table.setItem(row, column, item)
        self.sessions_table.setSortingEnabled(True)
        self.apply_filter()
        if selected is not None:
            self.select_pid(selected)
        blocked = sum(1 for session in sessions if session[8])
        active = sum(1 for session in sessions if session[5] == 'active')
        self.summary_label.setText(
            tr('{0} session(s), {1} active, {2} blocked').format(
                len(sessions), active, blocked))
        self.selection_changed()

    def apply_filter(self) -> None:
        hide_idle = self.active_chkbox.isChecked()
        for row in range(self.sessions_table.rowCount()):
            state = self.sessions_table.item(row, 5).text()
            blocked = self.sessions_table.item(row, 8).text()
            hidden = hide_idle and state == 'idle' and not blocked
            self.sessions_table.setRowHidden(row, hidden)

    def selected_pid(self) -> Optional[int]:
        rows = self.sessions_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.sessions_table.item(rows[0].row(), 0).data(PID_ROLE)

    def select_pid(self, pid: int) -> None:
        for row in range(self.sessions_table.rowCount()):
            if self.sessions_table.item(row, 0).data(PID_ROLE) == pid:
                self.sessions_table.selectRow(row)
                return

    def selection_changed(self) -> None:
        rows = self.sessions_table.selectionModel().selectedRows()
        item = self.sessions_table.item(rows[0].row(), 0) if rows else None
        own = bool(item.data(OWN_ROLE)) if item else False
        self.query_text.setPlainText(item.data(QUERY_ROLE) if item else '')
        self.cancel_btn.setEnabled(item is not None and not own)
        self.terminate_btn.setEnabled(item is not None and not own)

    def request_cancel(self) -> None:
        pid = self.selected_pid()
        if pid is not None:
            self.cancel_requested.emit(pid)

    def request_terminate(self) -> None:
        pid = self.selected_pid()
        if pid is not None:
            self.terminate_requested.emit(pid)
