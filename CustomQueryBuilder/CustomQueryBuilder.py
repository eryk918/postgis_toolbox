# -*- coding: utf-8 -*-
import functools
import os
from typing import List, Optional

from db_manager.db_manager import DBManager
from db_manager.db_plugins.plugin import BaseError, VectorTable
from db_manager.dlg_db_error import DlgDbError
from db_manager.dlg_query_builder import QueryBuilderDlg
from db_manager.dlg_sql_window import DlgSqlWindow
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QPushButton, QHBoxLayout
from qgis.core import Qgis
from qgis.gui import QgisInterface

from .UI.new_object_dialog import NewObjectDialog
from .UI.PostGISHelpDialog import PostGISHelpDialog
from ..utils import tr, plugin_dir, plugin_name, Qt, ask_question

QUERY_EDITOR_ICON = os.path.join(plugin_dir, 'icons', 'query_editor.svg')


class CustomQueryBuilder(QueryBuilderDlg):
    def __init__(self, iface: QgisInterface, db, parent=None,
                 reset: bool = False) -> None:
        super().__init__(iface, db, parent, reset)
        self.setWindowTitle(f'{plugin_name} - {tr("SQL Query Builder")}')
        self.setWindowIcon(QIcon(QUERY_EDITOR_ICON))
        self.help_dialog = PostGISHelpDialog(self)
        self.add_help_button()

    def add_help_button(self) -> None:
        layout = self.ui.functions.parentWidget().layout()
        position = layout.indexOf(self.ui.functions)
        layout.removeWidget(self.ui.functions)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.ui.functions)
        self.help_button = QPushButton('ℹ️', self.ui.functions.parentWidget())
        self.help_button.setMaximumSize(22, 22)
        self.help_button.setToolTip(
            tr('Show information about PostGIS features.'))
        self.help_button.clicked.connect(self.show_help)
        row.addWidget(self.help_button)
        layout.insertLayout(position, row)

    def function_names(self) -> List[str]:
        return [self.ui.functions.itemText(index)
                for index in range(1, self.ui.functions.count())]

    def show_help(self) -> None:
        self.help_dialog.run(self.function_names())

    def table_label(self, table) -> str:
        if table.schema() is None:
            return f'"{table.name}"'
        return f'"{table.schema().name}"."{table.name}"'

    def show_tables(self) -> None:
        self.update_table_list()
        self.ui.tables.clear()
        self.ui.tables.insertItems(0, [tr('Tables')])
        self.ui.tables.insertItems(
            1, [self.table_label(table) for table in self.tables])

    def add_tables(self) -> None:
        if self.ui.tables.currentIndex() <= 0:
            return
        selected_text = self.ui.tables.currentText()
        tables = [table for table in self.tables
                  if self.table_label(table) == selected_text]
        if len(tables) != 1:
            return
        self.table = tables[0]
        if self.table.name in self.coltables:
            response = ask_question(
                self,
                tr('Do you want to add table {0} again?').format(
                    selected_text))
            if not response:
                self.ui.tables.setCurrentIndex(0)
                return
        quoted_name = self.table.quotedName()
        current_text = self.ui.tab.text().strip()
        if current_text:
            self.ui.tab.setText(f'{current_text}, {quoted_name}')
        else:
            self.ui.tab.setText(quoted_name)
        self.ui.tables.setCurrentIndex(0)


class CustomDbSqlWindow(DlgSqlWindow):
    def __init__(self, iface: QgisInterface, db, parent=None) -> None:
        super().__init__(iface, db, parent)
        self.btnCreateTable = QPushButton(tr('Create a table'), self)
        self.btnCreateTable.setObjectName('btnCreateTable')
        self.buttonLayout.insertWidget(
            self.buttonLayout.indexOf(self.btnCreateView) + 1,
            self.btnCreateTable)
        self.btnCreateTable.clicked.connect(self.create_table)

    def schema_names(self) -> List[str]:
        schemas = self.db.schemas()
        if schemas is None:
            return []
        return [schema.name for schema in schemas]

    def ask_object_name(self, title: str, label: str) -> tuple:
        dialog = NewObjectDialog(title, label, self.schema_names(), self)
        if dialog.exec() != NewObjectDialog.Accepted:
            return None, None
        return dialog.schema_name(), dialog.object_name()

    def execute_ddl(self, sql: str) -> None:
        try:
            self.db.connector._execute_and_commit(sql)
            self.db.refresh()
        except BaseError as error:
            DlgDbError.showError(error, self)

    def create_table(self) -> None:
        schema, table = self.ask_object_name(
            tr('Create a table'), tr('Table name'))
        if not schema or not table:
            return
        self.execute_ddl(
            f'CREATE TABLE {self.db.connector.quoteId((schema, table))} '
            f'AS ({self._getExecutableSqlQuery()})')

    def createView(self) -> None:
        schema, view = self.ask_object_name(
            tr('Create a view'), tr('View name'))
        if not schema or not view:
            return
        self.execute_ddl(
            f'CREATE VIEW {self.db.connector.quoteId((schema, view))} '
            f'AS {self._getExecutableSqlQuery()}')

    def displayQueryBuilder(self) -> None:
        dialog = CustomQueryBuilder(
            self.iface, self.db, self, reset=self.queryBuilderFirst)
        self.queryBuilderFirst = False
        if dialog.exec() == CustomQueryBuilder.Accepted:
            self.editSql.setText(dialog.query)


class FilteredDBManager(DBManager):
    def __init__(self, iface: QgisInterface, parent=None) -> None:
        super().__init__(iface, parent)
        self.setWindowTitle(f'{plugin_name} - {tr("Query editor")}')
        self.setWindowIcon(QIcon(QUERY_EDITOR_ICON))
        self.keep_postgis_only()

    def keep_postgis_only(self) -> None:
        model = self.tree.model()
        model.beginResetModel()
        model.rootItem.childItems = [
            item for item in model.rootItem.childItems
            if item.getItemData().typeName() == 'postgis']
        model.endResetModel()

    def connection_index(self, connection_name: str) -> QModelIndex:
        model = self.tree.model()
        for row in range(model.rowCount(QModelIndex())):
            plugin_index = model.index(row, 0, QModelIndex())
            self.tree.setExpanded(plugin_index, True)
            for child_row in range(model.rowCount(plugin_index)):
                index = model.index(child_row, 0, plugin_index)
                if index.data() == connection_name:
                    return index
        return QModelIndex()

    def select_connection(self, connection_name: str) -> bool:
        index = self.connection_index(connection_name)
        if not index.isValid():
            return False
        self.tree.setExpanded(index, True)
        self.tree.setCurrentIndex(index)
        return self.tree.currentDatabase() is not None

    def runSqlWindow(self) -> Optional[CustomDbSqlWindow]:
        db = self.tree.currentDatabase()
        if db is None:
            self.infoBar.pushMessage(
                tr('No database selected or you are not connected to it.'),
                Qgis.Info, self.iface.messageTimeout())
            self.tabs.setCurrentIndex(0)
            return None
        query = CustomDbSqlWindow(self.iface, db, self)
        db_name = db.connection().connectionName()
        index = self.tabs.addTab(query, tr('Query ({0})').format(db_name))
        self.tabs.setTabIcon(index, db.connection().icon())
        self.tabs.setCurrentIndex(index)
        query.nameChanged.connect(
            functools.partial(self.update_query_tab_name, index, db_name))
        return query


class FilteredDBManagerPlugin:
    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.dlg = None

    def run(self) -> FilteredDBManager:
        if self.dlg is None:
            self.dlg = FilteredDBManager(self.iface)
            self.dlg.destroyed.connect(self.on_destroyed)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
        self.dlg.activateWindow()
        return self.dlg

    def on_destroyed(self, obj=None) -> None:
        self.dlg = None

    def close(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
