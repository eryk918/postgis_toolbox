# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PostGISToolbox
                                 A QGIS plugin
 Plugin for QGIS implementing selected PostGIS spatial functions
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
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

from qgis.PyQt.QtCore import QSettings, QCoreApplication, qVersion, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QLabel
from qgis.core import QgsApplication
from qgis.utils import iface

from .DBManager.DBManager import DBManager
from .ImportVector.ImportVector import ImportVector
from .ImportRaster.ImportRaster import ImportRaster
from .postgis_toolbox_provider import PostGISToolboxProvider
from .utils import tr, plugin_dir, get_active_db_info, create_pg_connecton, \
    plugin_name

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)


class PostGISToolboxPlugin(object):

    def __init__(self):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.provider = None
        self.plugin_dir = plugin_dir
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'pgtoolbox_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            translator = QTranslator()
            translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(translator)

        # self.dlg
        # self.dlg_settings

        self.actions = []
        self.menu = tr(f'&{plugin_name}')
        self.toolbar = self.iface.addToolBar(plugin_name)
        self.toolbar.setObjectName(plugin_name)
        self.db = None
        self.create_test_db()

    def create_test_db(self):
        self.db = create_pg_connecton(
            {'authcfg': '', 'database': 'test_postgis', 'host': 'localhost',
             'password': '4ZcVABhMHJEtytL8', 'port': '5432', 'service': '',
             'sslmode': 'SslAllow', 'username': 'admin_rpo',
             'connection_name': 'bdot'})

    def initProcessing(self):
        self.provider = PostGISToolboxProvider(self)
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

        self.add_action(
            os.path.join(self.plugin_dir, 'icons/manage_dbs.png'),
            text=tr('Manage databases'),
            callback=self.run_db_config,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'icons/import_vector_layer.png'),
            text=tr('Import vector data'),
            callback=self.run_import_vector,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'icons/import_raster_layers.png'),
            text=tr('Import raster data'),
            callback=self.run_import_raster,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'icons/history.png'),
            text=tr('History'),
            callback=self.run_history,
            parent=self.iface.mainWindow())

        self.add_action(
            os.path.join(self.plugin_dir, 'icons/settings.png'),
            text=tr(u'Settings'),
            callback=self.run_settings,
            parent=self.iface.mainWindow())

        self.connection_label = self.add_action(label=True)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
        for action in self.actions:
            self.iface.removePluginDatabaseMenu(
                tr('&PostGIS Toolbox'),
                action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def add_action(
            self,
            icon_path=None,
            text=None,
            callback=None,
            enabled_flag: bool = True,
            add_to_menu: bool = True,
            add_to_toolbar: bool = True,
            status_tip=None,
            whats_this=None,
            parent=None,
            label: bool = False):
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

    def run_history(self) -> None:
        pass
