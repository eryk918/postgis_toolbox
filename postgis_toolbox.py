# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PostGISToolbox
                                 A QGIS plugin
 Development of a QGIS plugin implementing selected PostGIS functions
                              -------------------
        begin                : 2022-05-12
        copyright            : (C) 2022 by Eryk Chełchowski
        email                : erwinek1998@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Eryk Chełchowski'
__date__ = '2022-05-12'
__copyright__ = '(C) 2022 by Eryk Chełchowski'

__revision__ = '$Format:%H$'

import inspect
import os
import sys

from qgis.PyQt.QtCore import QSettings, QCoreApplication, qVersion, \
    QTranslator, QModelIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QLabel, QMessageBox
from qgis.core import QgsApplication
from qgis.utils import iface

from .CustomQueryBuilder.CustomQueryBuilder import CustomQueryBuilder, \
    FilteredDBManagerPlugin
from .DBManager.DBManager import DBManager
from .ImportRaster.ImportRaster import ImportRaster
from .ImportVector.ImportVector import ImportVector
from .postgis_toolbox_provider import PostGISToolboxProvider
from .utils import tr, plugin_dir, get_active_db_info, plugin_name

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class PostGISToolboxPlugin(object):
    def __init__(self):
        self.db = None
        self.actions = []
        self.iface = iface
        self.provider = None
        self.plugin_dir = plugin_dir
        self.canvas = iface.mapCanvas()
        self._install_translator()
        self.menu = tr(f'&{plugin_name}')
        self.added_processing_connection = False
        self.toolbar = self.iface.addToolBar(plugin_name)
        self.toolbar.setObjectName(plugin_name)
        self.db_manager_plugin = FilteredDBManagerPlugin(self.iface)

    def initGui(self):
        self._initProcessing()
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'manage_dbs.png'),
            text=tr('Manage databases'),
            callback=self.run_db_config,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'import_vector_layer.png'),
            text=tr('Import vector data'),
            callback=self.run_import_vector,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'import_raster_layers.png'),
            text=tr('Import raster data'),
            callback=self.run_import_raster,
            parent=self.iface.mainWindow())
        self._add_action(
            os.path.join(self.plugin_dir, 'icons', 'query_editor.png'),
            text=tr('Query editor'),
            callback=self.run_query_editor,
            parent=self.iface.mainWindow())
        self.connection_label = self._add_action(label=True)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
        for action in self.actions:
            self.iface.removePluginDatabaseMenu(
                tr('&PostGIS Toolbox'),
                action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

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
            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

    def _add_action(
            self, icon_path=None, text=None, callback=None,
            enabled_flag: bool = True, add_to_menu: bool = True,
            add_to_toolbar: bool = True, status_tip=None, whats_this=None,
            parent=None, label: bool = False) -> QAction:

        if not label:
            icon = QIcon(icon_path)
            action = QAction(icon, text, parent)
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
        else:
            dummy_label = QLabel()
            get_active_db_info(self.db, dummy_label, True)
            action = QAction(QIcon(), dummy_label.text(), parent)
            action.setEnabled(False)
            if add_to_toolbar:
                self.toolbar.addAction(action)
        self.actions.append(action)
        return action

    def run_import_vector(self) -> None:
        self.import_vector = ImportVector(self)
        self.import_vector.run()

    def run_import_raster(self) -> None:
        self.import_raster = ImportRaster(self)
        self.import_raster.run()

    def run_db_config(self) -> None:
        self.db_manager = DBManager(self)
        self.db_manager.run()

    def run_settings(self) -> None:
        pass

    def run_query_editor(self) -> None:
        if not hasattr(self, 'db') or not self.db:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('There is no connection to the PostGIS database!'),
                QMessageBox.Ok)
            return
        self._open_db_manager()
        self._expand_query_sections()
        self.db_manager_plugin.dlg.runSqlWindow()
        sqlwindow = self.db_manager_plugin.dlg.tabs.currentWidget()
        try:
            sqlwindow.queryBuilderBtn.clicked.disconnect()
        except AttributeError:
            self.db_manager_plugin.dlg.close()
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('There is no connection to the PostGIS database!'),
                QMessageBox.Ok)
            return
        sqlwindow.queryBuilderBtn.clicked.connect(self._display_query_builder)
        self._display_query_builder()

    def _expand_query_sections(self) -> None:
        tree = self.db_manager_plugin.dlg.tree
        db_model = tree.model()
        top_idx = QModelIndex()
        for row in range(db_model.rowCount(QModelIndex())):
            top_idx = db_model.index(row, 0, QModelIndex())
            if top_idx.data() == 'PostGIS':
                break
        if not top_idx.isValid():
            return
        tree.setExpanded(top_idx, True)

        below_idx = db_model.treeView.indexBelow(top_idx)
        while below_idx.data() != self.db.connectionName():
            below_idx = tree.indexBelow(below_idx)
            if below_idx.data() is None:
                break
        if not below_idx.isValid():
            return
        tree.setExpanded(below_idx, True)

    def _open_db_manager(self) -> None:
        if not hasattr(self, 'db_manager_plugin'):
            return
        if self.db_manager_plugin.dlg is None:
            self.db_manager_plugin.run()
        else:
            self.db_manager_plugin.dlg.activateWindow()

    def _display_query_builder(self) -> None:
        parent = self.db_manager_plugin.dlg.tabs.currentWidget()
        self.query_dlg = CustomQueryBuilder(
            self, parent.db, parent, parent.queryBuilderFirst)
        parent.queryBuilderFirst = False
        result = self.query_dlg.exec_()
        if result:
            parent.editSql.setText(self.query_dlg.query)
