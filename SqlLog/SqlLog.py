# -*- coding: utf-8 -*-
from .UI.sql_log_dialog import SqlLogDialog
from ..utils import iface, Qt


class SqlLog:
    def __init__(self, parent) -> None:
        self.main = parent
        self.dlg = None

    def run(self) -> None:
        if self.dlg is None:
            self.dlg = SqlLogDialog(iface.mainWindow())
        self.dlg.refresh()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
        self.dlg.activateWindow()

    def close(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
