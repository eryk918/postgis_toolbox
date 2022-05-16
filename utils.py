# -*- coding: utf-8 -*-

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from typing import List, Any

from PyQt5.QtCore import Qt
from chardet import detect
from qgis.PyQt.QtCore import QCoreApplication, NULL
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtSql import QSqlDatabase, QSqlQuery
from qgis.PyQt.QtWidgets import QComboBox, QApplication, QProgressDialog, \
    QMessageBox, QPushButton, QProgressBar, QTreeWidgetItem
from qgis.core import QgsProject, QgsVectorLayer, \
    QgsRasterLayer, QgsApplication, Qgis, QgsMessageLog
from qgis.utils import iface

project = QgsProject.instance()

plugin_name = 'PostGIS Toolbox'
plugin_dir = os.path.dirname(__file__)
main_plugin_icon = QIcon(os.path.join(plugin_dir, 'icons', 'main.png'))

connection_key_names = [
    'authcfg', 'database', 'host', 'password', 'port', 'service',
    'sslmode', 'username', 'connection_name'
]

system_tables = ['pg_catalog', 'pg_toast_temp_1', 'pg_temp_1', 'pg_toast',
                 'information_schema', 'public', 'topology']

test_query = 'SELECT version();'


def tr(string):
    return QCoreApplication.translate('Processing', string)


class CreateTemporaryLayer(QgsVectorLayer):
    parent_layer = None

    def __init__(self, *args, **kwargs):
        super(CreateTemporaryLayer, self).__init__(*args, **kwargs)

    def set_layer_fields(self, fields):
        self.dataProvider().addAttributes(fields)
        self.updateFields()


def repair_comboboxes(dlg):
    dialog_obj_list = [dlg.__getattribute__(obj) for obj in dlg.__dir__()]
    combo_list = list(
        filter(lambda elem: isinstance(elem, QComboBox), dialog_obj_list))
    if not combo_list:
        return
    for combo in combo_list:
        combo.installEventFilter(dlg)
        temp_value = combo.isEditable()
        combo.setEditable(True)
        combo_css = 'QComboBox { combobox-popup: 0; }'
        combo.setStyleSheet(f"{combo.styleSheet()} {combo_css}")
        combo.setMaxVisibleItems(10)
        combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        combo.setEditable(temp_value)


def get_project_settings(parameter, key, default=''):
    return project.readEntry(parameter, key, default)[0]


def set_project_settings(parameter, key, value):
    return project.writeEntry(parameter, key, value)


def create_progress_bar(max_len, title='Please wait',
                        txt='Data is being processed...', start_val=0,
                        auto_close=True, cancel_btn=None, silent=False):
    progress_bar = QProgressDialog()
    progress_bar.setFixedWidth(500)
    progress_bar.setWindowTitle(title)
    progress_bar.setLabelText(txt)
    progress_bar.setMaximum(max_len)
    progress_bar.setValue(start_val)
    progress_bar.setAutoClose(auto_close)
    progress_bar.setCancelButton(cancel_btn)
    QApplication.processEvents()
    if silent:
        progress_bar.close()
    return progress_bar


def change_progressbar_value(progress, last_progress_value,
                             value, last_step=False, silent=False):
    if not silent:
        progress.show()
    QApplication.processEvents()
    last_progress_value += value
    if last_progress_value == 100 or last_step:
        progress.setValue(100)
        progress.close()
    else:
        progress.setValue(last_progress_value)


def change_alg_progress(progress, last_progress_value, value):
    QApplication.processEvents()
    last_progress_value += value
    if last_progress_value == 100:
        progress.setProgress(100)
    else:
        progress.setProgress(last_progress_value)
    return last_progress_value


def add_layer_into_map(layer, group_name, parent_name=None, position=0):
    root = project.layerTreeRoot()
    if parent_name and root.findGroup(parent_name):
        group = root.findGroup(parent_name).findGroup(group_name)
    else:
        group = root.findGroup(group_name)
    if not group:
        project.addMapLayer(layer)
        return
    QApplication.processEvents()
    project.addMapLayer(layer, False)
    if group_name:
        group.insertLayer(position, layer)
        group.setExpanded(False)


def add_rasters_to_project(group_name, list_of_rasters, symbology=None):
    QApplication.processEvents()
    group_import = project.layerTreeRoot().findGroup(group_name)
    if not group_import:
        project.layerTreeRoot().addGroup(group_name)
    for raster_path in list_of_rasters:
        QApplication.processEvents()
        rlayer = QgsRasterLayer(raster_path, os.path.basename(raster_path))
        add_layer_into_map(rlayer, group_name)
        if symbology:
            rlayer.loadNamedStyle(symbology)
            rlayer.triggerRepaint()
            iface.layerTreeView().refreshLayerSymbology(rlayer.id())


def add_vectors_to_project(group_name, list_of_vectors, symbology=None):
    QApplication.processEvents()
    group_import = project.layerTreeRoot().findGroup(group_name)
    if not group_import:
        project.layerTreeRoot().addGroup(group_name)
    for vector_path in list_of_vectors:
        QApplication.processEvents()
        if isinstance(vector_path, QgsVectorLayer):
            vlayer = vector_path
        else:
            vlayer = QgsVectorLayer(vector_path, os.path.basename(vector_path),
                                    "ogr")
        add_layer_into_map(vlayer, group_name)
        if symbology:
            vlayer.loadNamedStyle(symbology)
            vlayer.triggerRepaint()
            iface.layerTreeView().refreshLayerSymbology(vlayer.id())


def open_other_files(filepath):
    if sys.platform.startswith('darwin'):
        subprocess.call(('open', filepath))
    elif os.name == 'nt':
        try:
            os.startfile(filepath)
        except WindowsError:
            ext = os.path.splitext(filepath)[-1]
            QMessageBox.critical(
                None, 'PostGIS Toolbox',
                f'''Error opening a file with the file extension *.{ext}.''',
                QMessageBox.Ok)
            return
    elif os.name == 'posix':
        subprocess.call(('xdg-open', filepath))


def standarize_path(path):
    return os.path.normpath(os.sep.join(re.split(r'\\|/', path)))


def repair_encoding(tmp_dir, infile):
    tmp_file = os.path.join(
        tmp_dir,
        f"{datetime.now().strftime('%H_%M_%S_%f')[:-3]}.{os.path.splitext(infile)[-1]}"
    )
    shutil.copyfile(infile, tmp_file)
    os.remove(infile)
    with open(tmp_file, 'rb') as file:
        rawdata = rb''.join([file.readline() for _ in range(150)])
    with open(tmp_file,
              'r', encoding=detect(rawdata)['encoding']) as input_file, \
            open(infile, 'w', encoding='utf-8') as output_file:
        text = input_file.read()
        output_file.write(text)


def repair_path_for_exec(string):
    return string.replace('\\', '\\\\')


def throw_log_message(mess):
    QgsMessageLog.logMessage(mess, tag="PostGIS Toolbox")


def fill_item(item, value):
    def new_item(parent, text, val=None):
        child = QTreeWidgetItem([text])
        fill_item(child, val)
        parent.addChild(child)
        child.setExpanded(True)

    if value is None:
        return
    elif isinstance(value, dict):
        for key, val in sorted(value.items()):
            new_item(item, str(key), val)
    elif isinstance(value, (list, tuple)):
        if isinstance(value, list):
            value.sort()
        for val in value:
            new_item(item, val)
    else:
        new_item(item, str(value))


def get_all_tables_from_schema(db, schema_name) -> List:
    all_tables_result = make_query(db, f'''
        SELECT "table_name" 
        FROM information_schema.tables 
        WHERE table_schema = '{schema_name}' AND table_name NOT IN 
            ('_ogr_other_metadata', '_ogr_fields_metadata', 
            '_ogr_layers_metadata', '_ogr_layer_relationships');
    ''')
    list_of_tables = list(zip(*all_tables_result))[
        0] if all_tables_result else []
    return list(list_of_tables)


def get_schema_name_list_for_db(db: QSqlDatabase) -> List:
    if not db:
        return []
    if not db.isOpen():
        db.open()
    if not db.isOpen():
        return []
    schema_names_result = make_query(db, f'''
        SELECT schema_name 
        FROM information_schema.schemata
        WHERE schema_name NOT IN 
            ({','.join(f"'{name}'" for name in system_tables)});
    ''')
    list_to_cbbx = list(zip(*schema_names_result))[
        0] if schema_names_result else []
    return list(list_to_cbbx)


class NewThreadAlg:
    def __init__(self, info_dict, func_to_run, progress=False):
        self.info_dict = info_dict
        self.func_to_run = func_to_run
        self.progress = progress

    def start(self):
        self.msg = iface.messageBar().createMessage(
            self.info_dict['plugin_name'], self.info_dict['alg_name'])
        self.prog = QProgressBar(self.msg)
        if not self.progress:
            self.prog.setMaximum(0)
        self.btn_cancel = QPushButton(self.msg)
        self.btn_cancel.setText('Cancel')
        self.btn_cancel.clicked.connect(self.cancel)
        self.msg.layout().addWidget(self.prog)
        self.msg.layout().addWidget(self.btn_cancel)
        self.task = self.func_to_run
        self.task.begun.connect(
            lambda: iface.messageBar().pushWidget(self.msg, Qgis.Info))
        self.task.progressChanged.connect(
            lambda: self.prog.setValue(self.task.progress()))
        self.task.taskCompleted.connect(
            lambda: iface.messageBar().popWidget(self.msg))
        self.task.taskTerminated.connect(
            lambda: iface.messageBar().popWidget(self.msg))
        QgsApplication.taskManager().addTask(self.task)

    def cancel(self):
        self.task.cancel()


def create_pg_connecton(db_params: dict) -> QSqlDatabase:
    con = QSqlDatabase.addDatabase('QPSQL', db_params['connection_name'])
    con.setHostName(db_params['host'])
    con.setDatabaseName(db_params['database'])
    con.setPort(int(db_params['port']))
    con.setUserName(db_params['username'])
    con.setPassword(db_params['password'])
    con.open()
    return con


def make_query(db: QSqlDatabase, query: str, schema_name: str = ''):
    response = []
    if not db.isOpen():
        db.open()
    query_obj = QSqlQuery(db)
    if schema_name:
        query_obj.exec_(f'SET search_path TO "{schema_name}",public;')
    request = query_obj.exec_(query)
    if request:
        object_amount = query_obj.record().count()
        while query_obj.next():
            row = []
            for object_id in range(0, object_amount):
                val = query_obj.value(object_id)
                row.append(None if val == NULL else val)
            response.append(row)
    return response


def make_queries(sql_list, db, schema_name=''):
    query = QSqlQuery(db)
    if db.driverName() == "QPSQL":
        query.exec_(f"SET search_path TO {schema_name},public;")
    query.exec_('BEGIN;')
    for exp in sql_list:
        query.exec_(exp)
    query.exec_('COMMIT;')


def unpack_nested_lists(n_list: List[List[Any]]) -> List[Any]:
    return [elem for nested_list in n_list for elem in nested_list]
