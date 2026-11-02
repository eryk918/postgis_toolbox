# -*- coding: utf-8 -*-
import os
from datetime import datetime

from qgis.PyQt import uic
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QDialog, QApplication, QFileDialog

from ...utils import repair_dialog, tr, sql_log, clear_sql_log, Qt, \
    read_setting, save_setting, show_info, show_error

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'sql_log_dialog.ui'))


class SqlLogDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'sql_log.svg')
        self.setWindowFlags(Qt.Window)
        self.log_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.refresh_btn.clicked.connect(self.refresh)
        self.copy_btn.clicked.connect(self.copy_log)
        self.save_btn.clicked.connect(self.save_log)
        self.clear_btn.clicked.connect(self.clear_log)
        self.errors_chkbox.toggled.connect(self.refresh)

    def refresh(self) -> None:
        entries = sql_log
        if self.errors_chkbox.isChecked():
            entries = [entry for entry in entries if entry['error']]
        blocks = []
        for entry in entries:
            status = tr('ERROR') if entry['error'] else tr('OK')
            header = f"-- {entry['time']}  {status}  {entry['duration']} ms"
            if entry['error']:
                header += f"\n-- {entry['error']}"
            blocks.append(f"{header}\n{entry['sql']}")
        self.log_text.setPlainText('\n\n'.join(blocks))
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())
        errors = sum(1 for entry in sql_log if entry['error'])
        self.summary_label.setText(
            tr('{0} statements, {1} errors').format(len(sql_log), errors))

    def copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_text.toPlainText())

    def save_log(self) -> None:
        directory = read_setting('sql_log/export_dir', '') or ''
        default = os.path.join(
            directory,
            datetime.now().strftime('postgis_toolbox_%Y%m%d_%H%M%S.txt'))
        filters = ';;'.join([tr('Text files (*.txt)'),
                             tr('Log files (*.log)')])
        path, selected = QFileDialog.getSaveFileName(
            self, tr('Save SQL log'), default, filters)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += '.log' if '*.log' in selected else '.txt'
        try:
            with open(path, 'w', encoding='utf-8') as log_file:
                log_file.write(self.log_text.toPlainText())
        except OSError as error:
            show_error(self, tr('Saving the SQL log failed: {0}').format(
                error))
            return
        save_setting('sql_log/export_dir', os.path.dirname(path))
        show_info(self, tr('SQL log saved to {0}.').format(path))

    def clear_log(self) -> None:
        clear_sql_log()
        self.refresh()
