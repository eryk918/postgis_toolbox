# -*- coding: utf-8 -*-
import functools
import os
from functools import partial

from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import QAbstractItemModel, pyqtSignal, QModelIndex, Qt, \
    QSize, QSettings
from qgis.PyQt.QtGui import QIcon, QKeySequence
from qgis.PyQt.QtWidgets import QTreeView, QApplication, QToolBar, QMenu, \
    QStatusBar, QDockWidget, QSizePolicy, QSpacerItem, QGridLayout, QTabBar, \
    QTabWidget, QMenuBar, QDialog, QMessageBox, QPushButton, QInputDialog
from qgis.core import QgsVectorLayer, QgsDataSourceUri, QgsApplication, Qgis
from qgis.gui import QgsMessageBar, QgisInterface

from .db_manager.db_manager import DBManager
from .db_manager.db_manager_plugin import DBManagerPlugin
from .db_manager.db_model import PluginItem, TreeItem, DBModel
from .db_manager.db_plugins import supportedDbTypes, createDbPlugin
from .db_manager.db_plugins.plugin import Database, VectorTable, BaseError
from .db_manager.db_tree import DBTree
from .db_manager.dlg_db_error import DlgDbError
from .db_manager.dlg_query_builder import QueryBuilderDlg, FocusEventFilter
from .db_manager.dlg_sql_window import DlgSqlWindow
from .db_manager.info_viewer import InfoViewer
from .db_manager.layer_preview import LayerPreview
from .db_manager.table_viewer import TableViewer
from ..CustomQueryBuilder.UI.CustomQueryBuilderDialog import CustomQueryBuilderDialog

from ..utils import tr


class CustomQueryBuilder(QueryBuilderDlg):
    saveParameter = None

    def __init__(self, main_class, db, parent=None, reset=False) -> None:
        QDialog.__init__(self, parent)
        self.main_class = main_class
        self.plugin_dir = main_class.plugin_dir
        self.iface = main_class.iface
        self.db = db
        self.query = ''
        self.ui = CustomQueryBuilderDialog(self.main_class)
        self.ui.setupUi(self)
        self.ui.group.setMaximumHeight(self.ui.tab.sizeHint().height())
        self.ui.order.setMaximumHeight(self.ui.tab.sizeHint().height())

        self.evt = FocusEventFilter(self)
        self.ui.col.installEventFilter(self.evt)
        self.ui.where.installEventFilter(self.evt)
        self.ui.group.installEventFilter(self.evt)
        self.ui.order.installEventFilter(self.evt)

        connector_dict = self.db.connector.getQueryBuilderDictionary()
        self.table = None
        self.col_col = []
        self.col_where = []
        self.coltables = []
        self.ui.extract.setChecked(True)
        self.ui.functions.insertItems(1, connector_dict['function'])
        self.ui.math.insertItems(1, connector_dict['math'])
        self.ui.aggregates.insertItems(1, connector_dict['aggregate'])
        self.ui.operators.insertItems(1, connector_dict['operator'])
        self.ui.stringfct.insertItems(1, connector_dict['string'])

        if reset:
            QueryBuilderDlg.saveParameter = None
        if QueryBuilderDlg.saveParameter is not None:
            self.restoreLastQuery()

        self.show_tables()
        self.ui.aggregates.currentIndexChanged.connect(self.add_aggregate)
        self.ui.stringfct.currentIndexChanged.connect(self.add_stringfct)
        self.ui.operators.currentIndexChanged.connect(self.add_operators)
        self.ui.functions.currentIndexChanged.connect(self.add_functions)
        self.ui.math.currentIndexChanged.connect(self.add_math)
        self.ui.tables.currentIndexChanged.connect(self.add_tables)
        self.ui.tables.currentIndexChanged.connect(self.list_cols)
        self.ui.columns.currentIndexChanged.connect(self.add_columns)
        self.ui.columns_2.currentIndexChanged.connect(self.list_values)
        self.ui.reset.clicked.connect(self.reset)
        self.ui.extract.stateChanged.connect(self.list_values)
        self.ui.values.doubleClicked.connect(self.query_item)
        self.ui.buttonBox.accepted.connect(self.validate)
        self.ui.checkBox.stateChanged.connect(self.show_tables)

        if self.db.explicitSpatialIndex():
            self.tablesGeo = [table for table in self.tables if
                              isinstance(table, VectorTable)]
            tablesGeo = [f'"{table.name}"."{table.geomColumn}"' for table
                         in self.tablesGeo]
            self.idxTables = [table for table in self.tablesGeo if
                              table.hasSpatialIndex()]
            idxTables = [f'"{table.name}"."{table.geomColumn}"' for table
                         in self.idxTables]
            self.ui.table_target.insertItems(1, tablesGeo)
            self.ui.table_idx.insertItems(1, idxTables)
            self.ui.usertree.clicked.connect(self.use_rtree)
        else:
            self.ui.toolBox.setItemEnabled(2, False)
        self.setup_window()

    def add_tables(self) -> None:
        if self.ui.tables.currentIndex() <= 0:
            return
        selected_text = self.ui.tables.currentText()
        table_objects = []
        for table in self.tables:
            if len(selected_text.upper().split('.')) > 1:
                if f'"{table.schema().name.upper()}"."{table.name.upper()}"' \
                        == selected_text.upper():
                    table_objects.append(table)
            elif table.name.upper() == selected_text.upper():
                table_objects.append(table)
        if len(table_objects) != 1:
            return
        self.table = table_objects[0]
        if selected_text in self.coltables:
            response = QMessageBox.question(
                self,
                "Table already used",
                f"Do you want to add table {selected_text} again?",
                QMessageBox.Yes | QMessageBox.No
            )
            if response == QMessageBox.No:
                return
        selected_text = self.table.quotedName()
        txt = self.ui.tab.text()
        if txt is None or txt in ("", " "):
            self.ui.tab.setText(f'{selected_text}')
        else:
            self.ui.tab.setText(f'{txt}, {selected_text}')
        self.ui.tables.setCurrentIndex(0)

    def update_table_list(self) -> None:
        self.tables = []
        add_sys_tables = self.ui.checkBox.isChecked()
        schemas = self.db.schemas()
        if schemas is None:
            self.tables = self.db.tables(None, add_sys_tables)
        else:
            for schema in schemas:
                self.tables += self.db.tables(schema, add_sys_tables)

    def show_tables(self) -> None:
        self.update_table_list()
        self.ui.tables.clear()
        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            self.ui.tables.insertItems(
                0, [QApplication.translate("DBManager", 'Tabele')])
        else:
            self.ui.tables.insertItems(
                0, [QApplication.translate("DBManager", 'Tables')])
        self.ui.tables.insertItems(
            1, [f'"{table.schema().name}"."{table.name}"' for table in
                self.tables])

    def list_cols(self) -> None:
        table = self.table
        if table is None:
            return
        if table.name in self.coltables:
            return
        columns = [f'"{table.name}"."{col.name}"' for col in table.fields()]
        columns = [f'"{table.name}".*'] + columns
        self.coltables.append(table.name)
        end = self.ui.columns.count()
        self.ui.columns.insertItems(end, columns)
        self.ui.columns_2.insertItems(end, columns)
        end = self.ui.columns.count()
        self.ui.columns.insertSeparator(end)
        self.ui.columns_2.insertSeparator(end)

    def setup_window(self) -> None:
        icon = QIcon(os.path.join(self.plugin_dir, 'icons/query_editor.png'))
        self.main_class.db_manager_plugin.dlg.setWindowIcon(icon)
        self.setWindowIcon(icon)


class PostGISDBModel(DBModel):
    importVector = pyqtSignal(QgsVectorLayer, Database, QgsDataSourceUri,
                              QModelIndex)
    notPopulated = pyqtSignal(QModelIndex)

    def __init__(self, parent=None) -> None:
        global isImportVectorAvail
        QAbstractItemModel.__init__(self, parent)
        self.treeView = parent
        self.header = [QApplication.translate("DBManager", '&Databases')]
        self.hasSpatialiteSupport = "spatialite" in supportedDbTypes()
        self.hasGPKGSupport = "gpkg" in supportedDbTypes()
        self.rootItem = TreeItem(None, None)
        for dbtype in ['postgis', 'vlayers']:
            item = PluginItem(createDbPlugin(dbtype), self.rootItem)
            item.changed.connect(partial(self.refreshItem, item))


class FilteredDBTree(DBTree):
    selectedItemChanged = pyqtSignal(object)

    def __init__(self, mainWindow) -> None:
        DBTree.__init__(self, mainWindow)
        self.mainWindow = mainWindow
        self.setModel(PostGISDBModel(self))
        self.setHeaderHidden(True)
        self.setEditTriggers(
            QTreeView.EditKeyPressed | QTreeView.SelectedClicked)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.doubleClicked.connect(self.addLayer)
        self.selectionModel().currentChanged.connect(self.currentItemChanged)
        self.expanded.connect(self.itemChanged)
        self.collapsed.connect(self.itemChanged)
        self.model().dataChanged.connect(self.modelDataChanged)
        self.model().notPopulated.connect(self.collapse)


class FilteredDBManager(DBManager):
    def __init__(self, parent) -> None:
        super(FilteredDBManager, self).__init__(parent)

    def setupUi(self) -> None:
        self.setWindowTitle(tr("PostGIS Toolbox - Query editor"))
        self.resize(QSize(700, 500).expandedTo(self.minimumSizeHint()))
        self._create_tabs()
        tabbar = self.tabs.tabBar()
        for btn_idx in range(3):
            btn = tabbar.tabButton(btn_idx, QTabBar.RightSide) \
                if tabbar.tabButton(btn_idx, QTabBar.RightSide) \
                else tabbar.tabButton(btn_idx, QTabBar.LeftSide)
            btn.resize(0, 0)
            btn.hide()
        spacerItem = QSpacerItem(
            20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.layout = QGridLayout(self.info)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addItem(spacerItem, 1, 0, 1, 1)
        self.infoBar = QgsMessageBar(self.info)
        self.infoBar.setSizePolicy(sizePolicy)
        self.layout.addWidget(self.infoBar, 0, 0, 1, 1)
        self.dock = QDockWidget(
            QApplication.translate("DBManager", "Providers"), self)
        self.dock.setObjectName("DB_Manager_DBView")
        self.dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.tree = FilteredDBTree(self)
        self.dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        self.menuBar = QMenuBar(self)
        self.menuDb = QMenu(
            QApplication.translate("DBManager", "&Database"), self)
        self.menuBar.addMenu(self.menuDb)
        self.menuSchema = QMenu(
            QApplication.translate("DBManager", "&Schema"), self)
        self.menuTable = QMenu(
            QApplication.translate("DBManager", "&Table"), self)
        self.menuHelp = None
        self.setMenuBar(self.menuBar)
        self.toolBar = QToolBar(
            QApplication.translate("DBManager", "&Default"), self)
        self.toolBar.setObjectName("DB_Manager_ToolBar")
        self.addToolBar(self.toolBar)
        self._create_actions()

    def _create_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.info = InfoViewer(self)
        self.table = TableViewer(self)
        self.preview = LayerPreview(self)
        self.tabs.addTab(self.info,
                         QApplication.translate("DBManager", "Info"))
        self.tabs.addTab(self.table,
                         QApplication.translate("DBManager", "Table"))
        self.tabs.addTab(self.preview,
                         QApplication.translate("DBManager", "Preview"))
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)

    def _create_actions(self) -> None:
        sep = self.menuDb.addSeparator()
        sep.setObjectName("DB_Manager_DbMenu_placeholder")
        sep.setVisible(False)
        actionMenuSchema = self.menuBar.addMenu(self.menuSchema)
        actionMenuSchema.setVisible(False)
        actionMenuTable = self.menuBar.addMenu(self.menuTable)
        actionMenuTable.setVisible(False)
        self.actionRefresh = self.menuDb.addAction(
            QgsApplication.getThemeIcon("/mActionRefresh.svg"),
            QApplication.translate("DBManager", "&Refresh"),
            self.refreshActionSlot, QKeySequence("F5"))
        self.actionSqlWindow = self.menuDb.addAction(
            QIcon(":/db_manager/actions/sql_window"),
            QApplication.translate("DBManager", "&SQL Window"),
            self.runSqlWindow, QKeySequence("F2"))
        self.menuDb.addSeparator()
        self.actionClose = self.menuDb.addAction(
            QIcon(), QApplication.translate("DBManager", "&Exit"),
            self.close,
            QKeySequence("CTRL+Q"))
        sep = self.menuSchema.addSeparator()
        sep.setObjectName("DB_Manager_SchemaMenu_placeholder")
        sep.setVisible(False)
        sep = self.menuTable.addSeparator()
        sep.setObjectName("DB_Manager_TableMenu_placeholder")
        sep.setVisible(False)
        self.actionImport = self.menuTable.addAction(
            QIcon(":/db_manager/actions/import"),
            QApplication.translate("DBManager", "&Import Layer/File…"),
            self.importActionSlot)
        self.actionExport = self.menuTable.addAction(
            QIcon(":/db_manager/actions/export"),
            QApplication.translate("DBManager", "&Export to File…"),
            self.exportActionSlot)
        self.menuTable.addSeparator()
        self.toolBar.addAction(self.actionRefresh)
        self.toolBar.addAction(self.actionSqlWindow)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.actionImport)
        self.toolBar.addAction(self.actionExport)

    def runSqlWindow(self) -> None:
        db = self.tree.currentDatabase()
        if db is None:
            self.infoBar.pushMessage(
                QApplication.translate(
                    "DBManager",
                    "No database selected or you are not connected to it."
                ),
                Qgis.Info,
                self.iface.messageTimeout()
            )
            self.tabs.setCurrentIndex(0)
            return

        query = CustomDbSqlWindow(self.iface, db, self)
        dbname = db.connection().connectionName()
        tabname = QApplication.translate("DBManager", "Query ({0})").format(
            dbname)
        index = self.tabs.addTab(query, tabname)
        self.tabs.setTabIcon(index, db.connection().icon())
        self.tabs.setCurrentIndex(index)
        query.nameChanged.connect(
            functools.partial(self.update_query_tab_name, index, dbname))


class CustomDbSqlWindow(DlgSqlWindow):
    def __init__(self, iface: QgisInterface, db, parent=None) -> None:
        super(CustomDbSqlWindow, self).__init__(iface, db, parent)
        self.btnCreateTable = QPushButton(
            QApplication.translate("DBManager", "Create a table"),
            self.layoutWidget)
        self.btnCreateTable.setObjectName("btnCreateTable")
        self.buttonLayout.insertWidget(3, self.btnCreateTable)
        self.btnCreateTable.clicked.connect(self.create_table)
        if self._createViewAvailable:
            self.btnCreateView.clicked.connect(self.create_view)
        _translate = QtCore.QCoreApplication.translate
        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            self.btnCreateTable.setText(
                QApplication.translate("DBManager", "Utwórz tabelę"))
            self.label_2.setText(
                QApplication.translate("DbManagerDlgSqlWindow", "Nazwa"))
            self.presetDelete.setText(
                QApplication.translate("DbManagerDlgSqlWindow", "Usuń"))
            if self.allowMultiColumnPk:
                self.uniqueColumnCheck.setText(
                    QApplication.translate(
                        "DBManager", "Kolumny z unikalnymi wartościami"))
            else:
                self.uniqueColumnCheck.setText(
                    QApplication.translate(
                        "DBManager", "Kolumna z unikalnymi wartościami"))

    def loadAsLayerToggled(self, checked) -> None:
        self.loadAsLayerGroup.setChecked(checked)
        self.loadAsLayerWidget.setVisible(checked)

    def create_table(self):
        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            table_name, response = QInputDialog.getText(
                None, QApplication.translate(
                    "DBManager", "Stwórz tabelę na podstawie zapytania."),
                QApplication.translate("DBManager", "Nazwa tabeli"))
        else:
            table_name, response = QInputDialog.getText(
                None, self.tr("Table name"), self.tr("Table name"))
        if response:
            try:
                self.db.connector.create_table(table_name,
                                               self._getExecutableSqlQuery())
            except BaseError as e:
                DlgDbError.showError(e, self)

    def create_view(self):
        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            view_name, response = QInputDialog.getText(
                None, QApplication.translate(
                    "DBManager", "Stwórz widok na podstawie zapytania."),
                QApplication.translate("DBManager", "Nazwa widoku"))
        else:
            view_name, response = QInputDialog.getText(
                None, self.tr("View name"), self.tr("View name"))
        if response:
            try:
                self.db.connector.createSpatialView(
                    view_name, self._getExecutableSqlQuery())
            except BaseError as e:
                DlgDbError.showError(e, self)


class FilteredDBManagerPlugin(DBManagerPlugin):
    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.dlg = None

    def run(self) -> None:
        if self.dlg is None:
            self.dlg = FilteredDBManager(self.iface)
            self.dlg.destroyed.connect(self.onDestroyed)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
        self.dlg.activateWindow()
