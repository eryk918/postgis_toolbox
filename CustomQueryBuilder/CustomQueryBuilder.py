# -*- coding: utf-8 -*-
import os
from functools import partial

from plugins.db_manager.db_manager import DBManager
from plugins.db_manager.db_manager_plugin import DBManagerPlugin
from plugins.db_manager.db_model import PluginItem, TreeItem, DBModel
from plugins.db_manager.db_plugins import supportedDbTypes, createDbPlugin
from plugins.db_manager.db_plugins.plugin import Database
from plugins.db_manager.db_tree import DBTree
from plugins.db_manager.dlg_query_builder import QueryBuilderDlg
from plugins.db_manager.info_viewer import InfoViewer
from plugins.db_manager.layer_preview import LayerPreview
from plugins.db_manager.table_viewer import TableViewer
from plugins.db_manager.ui.ui_DlgQueryBuilder import \
    Ui_DbManagerQueryBuilderDlg
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QAbstractItemModel, \
    pyqtSignal, QModelIndex, Qt, QSize
from qgis.PyQt.QtGui import QIcon, QKeySequence
from qgis.PyQt.QtWidgets import QTreeView, QApplication, QToolBar, QMenu, \
    QStatusBar, QDockWidget, QSizePolicy, QSpacerItem, QGridLayout, QTabBar, \
    QTabWidget, QMenuBar
from qgis.core import QgsVectorLayer, QgsDataSourceUri, QgsApplication
from qgis.gui import QgsMessageBar


class CustomQueryBuilder(QueryBuilderDlg):
    def __init__(self, main_class, db, parent=None, reset=False):
        super(CustomQueryBuilder, self).__init__(
            main_class.iface, db, parent, reset)
        self.main_class = main_class
        self.plugin_dir = main_class.plugin_dir
        self.setup_window()

    def setup_window(self) -> None:
        icon = QIcon(os.path.join(self.plugin_dir, 'icons/query_editor.png'))
        self.main_class.db_manager_plugin.dlg.setWindowIcon(icon)
        self.setWindowIcon(icon)
        self.retranslateUi(self.ui)

    def retranslateUi(self, interface: Ui_DbManagerQueryBuilderDlg):
        _translate = QCoreApplication.translate
        interface.label.setText(_translate("QueryBuilderDlg", "Select"))
        interface.label_2.setText(_translate("QueryBuilderDlg", "From"))
        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            interface.tables.setItemText(
                0, _translate("QueryBuilderDlg", "Tabele"))
            interface.columns.setItemText(
                0, _translate("QueryBuilderDlg", "Kolumny"))
            interface.columns_2.setItemText(
                0, _translate("QueryBuilderDlg", "Kolumny"))


class PostGISDBModel(DBModel):
    importVector = pyqtSignal(QgsVectorLayer, Database, QgsDataSourceUri,
                              QModelIndex)
    notPopulated = pyqtSignal(QModelIndex)

    def __init__(self, parent=None):
        global isImportVectorAvail

        QAbstractItemModel.__init__(self, parent)
        self.treeView = parent
        self.header = [self.tr('Databases')]

        self.hasSpatialiteSupport = "spatialite" in supportedDbTypes()
        self.hasGPKGSupport = "gpkg" in supportedDbTypes()

        self.rootItem = TreeItem(None, None)
        for dbtype in ['postgis', 'vlayers']:
            dbpluginclass = createDbPlugin(dbtype)
            item = PluginItem(dbpluginclass, self.rootItem)
            item.changed.connect(partial(self.refreshItem, item))


class FilteredDBTree(DBTree):
    selectedItemChanged = pyqtSignal(object)

    def __init__(self, mainWindow):
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
    def __init__(self, parent):
        super(FilteredDBManager, self).__init__(parent)

    def setupUi(self):
        self.setWindowTitle(self.tr("Query editor"))
        self.setWindowIcon(QIcon(":/db_manager/icon"))
        self.resize(QSize(700, 500).expandedTo(self.minimumSizeHint()))
        self.tabs = QTabWidget()
        self.info = InfoViewer(self)
        self.tabs.addTab(self.info, self.tr("Info"))
        self.table = TableViewer(self)
        self.tabs.addTab(self.table, self.tr("Table"))
        self.preview = LayerPreview(self)
        self.tabs.addTab(self.preview, self.tr("Preview"))
        self.setCentralWidget(self.tabs)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        tabbar = self.tabs.tabBar()
        for btn_idx in range(3):
            btn = tabbar.tabButton(btn_idx, QTabBar.RightSide) \
                if tabbar.tabButton(btn_idx, QTabBar.RightSide) \
                else tabbar.tabButton(btn_idx, QTabBar.LeftSide)
            btn.resize(0, 0)
            btn.hide()
        self.layout = QGridLayout(self.info)
        self.layout.setContentsMargins(0, 0, 0, 0)
        spacerItem = QSpacerItem(
            20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.layout.addItem(spacerItem, 1, 0, 1, 1)
        self.infoBar = QgsMessageBar(self.info)
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.infoBar.setSizePolicy(sizePolicy)
        self.layout.addWidget(self.infoBar, 0, 0, 1, 1)
        self.dock = QDockWidget(self.tr("Providers"), self)
        self.dock.setObjectName("DB_Manager_DBView")
        self.dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.tree = FilteredDBTree(self)
        self.dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        self.menuBar = QMenuBar(self)
        self.menuDb = QMenu(self.tr("&Database"), self)
        self.menuBar.addMenu(self.menuDb)
        self.menuSchema = QMenu(self.tr("&Schema"), self)
        actionMenuSchema = self.menuBar.addMenu(self.menuSchema)
        self.menuTable = QMenu(self.tr("&Table"), self)
        actionMenuTable = self.menuBar.addMenu(self.menuTable)
        self.menuHelp = None
        self.setMenuBar(self.menuBar)
        self.toolBar = QToolBar(self.tr("Default"), self)
        self.toolBar.setObjectName("DB_Manager_ToolBar")
        self.addToolBar(self.toolBar)
        sep = self.menuDb.addSeparator()
        sep.setObjectName("DB_Manager_DbMenu_placeholder")
        sep.setVisible(False)
        self.actionRefresh = self.menuDb.addAction(
            QgsApplication.getThemeIcon("/mActionRefresh.svg"),
            self.tr("&Refresh"),
            self.refreshActionSlot, QKeySequence("F5"))
        self.actionSqlWindow = self.menuDb.addAction(
            QIcon(":/db_manager/actions/sql_window"), self.tr("&SQL Window"),
            self.runSqlWindow, QKeySequence("F2"))
        self.menuDb.addSeparator()
        self.actionClose = self.menuDb.addAction(
            QIcon(), self.tr("&Exit"),
            self.close,
            QKeySequence("CTRL+Q"))
        sep = self.menuSchema.addSeparator()
        sep.setObjectName("DB_Manager_SchemaMenu_placeholder")
        sep.setVisible(False)
        actionMenuSchema.setVisible(False)
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
        actionMenuTable.setVisible(False)
        self.toolBar.addAction(self.actionRefresh)
        self.toolBar.addAction(self.actionSqlWindow)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.actionImport)
        self.toolBar.addAction(self.actionExport)


class FilteredDBManagerPlugin(DBManagerPlugin):

    def __init__(self, iface):
        self.iface = iface
        self.dlg = None

    def run(self):
        if self.dlg is None:
            self.dlg = FilteredDBManager(self.iface)
            self.dlg.destroyed.connect(self.onDestroyed)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
        self.dlg.activateWindow()
