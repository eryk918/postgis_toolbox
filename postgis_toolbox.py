# -*- coding: utf-8 -*-

import inspect
import os
import sys
from typing import Optional

from qgis.PyQt.QtCore import QSettings, QCoreApplication, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QLabel
from qgis.core import QgsApplication, Qgis
from qgis.utils import iface

from .CustomQueryBuilder.CustomQueryBuilder import FilteredDBManagerPlugin
from .DBManager.DBManager import DBManager
from .ImportRaster.ImportRaster import ImportRaster
from .ImportVector.ImportVector import ImportVector
from .SqlLog.SqlLog import SqlLog
from .TableRegistry.TableRegistry import TableRegistry
from .postgis_toolbox_provider import PostGISToolboxProvider
from .utils import tr, plugin_dir, get_active_db_info, plugin_name, \
    show_error, connection_uri, save_setting

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class PostGISToolboxPlugin(object):
    def __init__(self):
        self.db = None
        self.connection_name = None
        self.db_manager = None
        self.actions = []
        self.iface = iface
        self.provider = None
        self.plugin_dir = plugin_dir
        self.canvas = iface.mapCanvas()
        self._install_translator()
        self.menu = tr(f'&{plugin_name}')
        self.toolbar = self.iface.addToolBar(plugin_name)
        self.toolbar.setObjectName(plugin_name)
        self.db_manager_plugin = FilteredDBManagerPlugin(self.iface)
        self.table_registry = TableRegistry(self)
        self.sql_log = SqlLog(self)

    def initGui(self):
        self._initProcessing()
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'manage_dbs.svg'),
            text=tr('Manage databases'),
            callback=self.run_db_config,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'import_vector_layer.svg'),
            text=tr('Import vector data'),
            callback=self.run_import_vector,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'import_raster_layers.svg'),
            text=tr('Import raster data'),
            callback=self.run_import_raster,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'table_registry.svg'),
            text=tr('Table registry'),
            callback=self.run_table_registry,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'query_editor.svg'),
            text=tr('Query editor'),
            callback=self.run_query_editor,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'sql_log.svg'),
            text=tr('SQL log'),
            callback=self.sql_log.run,
            parent=self.iface.mainWindow())
        self.connection_label = self._add_connection_label()
        self.disconnect_action = self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'disconnect_db.svg'),
            text=tr('Disconnect from database'),
            callback=self.disconnect_db,
            enabled_flag=False,
            parent=self.iface.mainWindow())

    def unload(self):
        self.db_manager_plugin.close()
        self.table_registry.close()
        self.sql_log.close()
        self.db = None
        self.connection_name = None
        QgsApplication.processingRegistry().removeProvider(self.provider)
        for action in self.actions:
            self.iface.removePluginDatabaseMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.iface.mainWindow().removeToolBar(self.toolbar)
        self.toolbar.deleteLater()

    def _initProcessing(self):
        self.provider = PostGISToolboxProvider(self)
        QgsApplication.processingRegistry().addProvider(self.provider)

    def _install_translator(self) -> None:
        locale = 'en'
        try:
            loc = str(QSettings().value('locale/userLocale'))
            if len(locale) > 1:
                locale = loc[:2]
        except Exception:
            return
        trans_path = os.path.join(self.plugin_dir, 'i18n', f'{locale}.qm')
        if os.path.exists(trans_path):
            self.translator = QTranslator()
            self.translator.load(trans_path)
            QCoreApplication.installTranslator(self.translator)

    def _add_action(
            self, icon_path: str, text: str, callback,
            enabled_flag: bool = True, add_to_menu: bool = True,
            add_to_toolbar: bool = True, status_tip=None, whats_this=None,
            parent=None) -> QAction:
        action = QAction(QIcon(icon_path), text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip is not None:
            action.setStatusTip(status_tip)
        if whats_this is not None:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.toolbar.addAction(action)
        if add_to_menu:
            self.iface.addPluginToDatabaseMenu(self.menu, action)
        self.actions.append(action)
        return action

    def _add_connection_label(self) -> QLabel:
        label = QLabel(self.toolbar)
        label.setContentsMargins(6, 0, 6, 0)
        get_active_db_info(self.db, label, True)
        self.toolbar.addWidget(label)
        return label

    def run_import_vector(self) -> None:
        self.import_vector = ImportVector(self)
        self.import_vector.run()

    def run_import_raster(self) -> None:
        self.import_raster = ImportRaster(self)
        self.import_raster.run()

    def run_db_config(self) -> None:
        self.db_manager = DBManager(self)
        self.db_manager.run()

    def run_table_registry(self) -> None:
        self.table_registry.run()

    def set_active_db(self, db, connection_name: Optional[str]) -> None:
        self.db = db
        self.connection_name = connection_name
        if self.db is not None and connection_name:
            save_setting('last/connection', connection_name)
            save_setting('last/database', connection_uri(self.db).database())
        get_active_db_info(self.db, self.connection_label, True)
        self.disconnect_action.setEnabled(self.db is not None)
        self.provider.refreshAlgorithms()
        self.table_registry.sync_active_db()

    def disconnect_db(self) -> None:
        if not self.db:
            return
        db_name = connection_uri(self.db).database()
        self.set_active_db(None, None)
        if self.db_manager is not None:
            self.db_manager.sync_active_db()
        iface.messageBar().pushMessage(
            plugin_name,
            tr('Disconnected from database {0}.').format(db_name),
            Qgis.Info, 3)

    def run_query_editor(self) -> None:
        if not self.db:
            show_error(
                iface.mainWindow(),
                tr('There is no connection to the PostGIS database!'))
            return
        manager = self.db_manager_plugin.run()
        if not manager.select_connection(self.connection_name):
            self.db_manager_plugin.close()
            show_error(
                iface.mainWindow(),
                tr('There is no connection to the PostGIS database!'))
            return
        sql_window = manager.runSqlWindow()
        if sql_window is not None:
            sql_window.displayQueryBuilder()
