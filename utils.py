# -*- coding: utf-8 -*-

import os
import os.path
import re
import shutil
import subprocess
import sys
from typing import List, Tuple, Any, Dict, Optional

import qgis
from PyQt5.QtCore import Qt
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QComboBox, QProgressBar, QTreeWidgetItem, \
    QDialog, QRadioButton, QToolButton, QCheckBox, QWidget
from qgis.PyQt.QtWidgets import QProgressDialog, QPushButton, QMessageBox, \
    QApplication, QLabel
from qgis.core import QgsMessageLog, Qgis, QgsDataSourceUri, QgsWkbTypes, \
    QgsProviderRegistry, QgsProviderMetadata, QgsProviderConnectionException, \
    QgsAbstractDatabaseProviderConnection
from qgis.core import QgsProject, QgsVectorLayer, \
    QgsRasterLayer, QgsApplication
from qgis.utils import iface

project = QgsProject.instance()
root = project.layerTreeRoot()
main_window = iface.mainWindow()

plugin_name = 'PostGIS Toolbox'
plugin_dir = os.path.dirname(__file__)
plugin_dir_name = 'postgis_toolbox'
main_plugin_icon = QIcon(os.path.join(plugin_dir, 'icons', 'main.svg'))

system_tables = ['pg_catalog', 'pg_toast_temp_1', 'pg_temp_1', 'pg_toast',
                 'information_schema', 'public', 'topology']


def tr(text: str):
    return QCoreApplication.translate('@default', text)


PROCESSING_LAYERS_GROUP = tr('PROCESSING_LAYERS')
RASTERS_LAYERS_GROUP = tr("IMPORTED RASTERS")
VECTORS_LAYERS_GROUP = tr("IMPORTED VECTORS")


def message_box(parent: Optional[QWidget], text: str,
                icon: int = QMessageBox.Information,
                buttons: int = QMessageBox.Ok,
                default: int = QMessageBox.NoButton,
                details: str = None) -> int:
    box = QMessageBox(icon, plugin_name, text, buttons, parent)
    window_icon = parent.windowIcon() \
        if parent is not None and parent is not iface.mainWindow() \
        else QIcon()
    box.setWindowIcon(
        main_plugin_icon if window_icon.isNull() else window_icon)
    if default != QMessageBox.NoButton:
        box.setDefaultButton(default)
    if details:
        box.setDetailedText(details)
    return box.exec()


def show_info(parent: Optional[QWidget], text: str,
              details: str = None) -> None:
    message_box(parent, text, QMessageBox.Information, details=details)


def show_warning(parent: Optional[QWidget], text: str) -> None:
    message_box(parent, text, QMessageBox.Warning)


def show_error(parent: Optional[QWidget], text: str) -> None:
    message_box(parent, text, QMessageBox.Critical)


def ask_question(parent: Optional[QWidget], text: str) -> bool:
    return message_box(
        parent, text, QMessageBox.Question,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


def repair_dialog(dlg: QDialog, icon_file: str = None,
                  translate_dialog: bool = True) -> None:
    dialog_obj_list = [dlg.__getattribute__(obj) for obj in dlg.__dir__()]

    if translate_dialog:
        for obj in dialog_obj_list:
            data = get_dialog_label_values(obj)
            if not data:
                continue
            set_dialog_labels(obj, tr(data))

    if icon_file:
        dlg.setWindowIcon(QIcon(
            os.path.join(plugin_dir, 'icons', icon_file)))
    else:
        dlg.setWindowIcon(main_plugin_icon)


def create_progress_bar(
        max_len, title=tr('Please wait'), txt=tr('Data is being processed...'),
        start_val=0, auto_close=True, cancel_btn=None, silent=False,
        parent: QWidget = None, width: int = None) -> QProgressDialog:
    progress_bar = QProgressDialog(parent)
    if width:
        progress_bar.setFixedWidth(width)
    progress_bar.setWindowTitle(f"{plugin_name} - {title}")
    progress_bar.setWindowIcon(
        parent.windowIcon() if parent else main_plugin_icon)
    progress_bar.setLabelText(txt)
    progress_bar.setMaximum(max_len)
    progress_bar.setValue(start_val)
    progress_bar.setAutoClose(auto_close)
    progress_bar.setCancelButton(cancel_btn)
    QApplication.processEvents()
    if silent:
        progress_bar.close()
    return progress_bar


def change_alg_progress(progress, last_progress_value, value):
    last_progress_value += value
    progress.setProgress(min(last_progress_value, 100))
    return last_progress_value


def add_layer_into_map(layer, group_name, parent_name=None, position=0,
                       raster: bool = False):
    if raster:
        project.addMapLayer(layer)
    else:
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
    QApplication.processEvents()


def add_rasters_to_project(group_name: str,
                           list_of_rasters: List[str or QgsRasterLayer],
                           symbology: str = None,
                           postgis_raster: bool = False) -> None:
    QApplication.processEvents()
    for raster in list_of_rasters:
        QApplication.processEvents()
        rlayer = raster if postgis_raster \
            else QgsRasterLayer(raster, os.path.basename(raster))
        add_layer_into_map(rlayer, group_name, raster=True)
        if symbology:
            rlayer.loadNamedStyle(symbology)
            rlayer.triggerRepaint()
            iface.layerTreeView().refreshLayerSymbology(rlayer.id())


def add_vectors_to_project(group_name: str,
                           list_of_vectors: List[str or QgsVectorLayer],
                           symbology: str = None) -> None:
    QApplication.processEvents()
    group_import = project.layerTreeRoot().findGroup(group_name)
    if not group_import:
        project.layerTreeRoot().addGroup(group_name)
    for vector_path in list_of_vectors:
        QApplication.processEvents()
        vlayer = vector_path if isinstance(vector_path, QgsVectorLayer) \
            else QgsVectorLayer(vector_path, os.path.basename(vector_path),
                                "ogr")
        add_layer_into_map(vlayer, group_name)
        if symbology:
            vlayer.loadNamedStyle(symbology)
            vlayer.triggerRepaint()
            iface.layerTreeView().refreshLayerSymbology(vlayer.id())


def open_other_files(filepath: str) -> None:
    if sys.platform.startswith('darwin'):
        subprocess.call(('open', filepath))
    elif os.name == 'nt':
        try:
            os.startfile(filepath)
        except WindowsError:
            ext = os.path.splitext(filepath)[-1]
            show_error(
                None,
                tr('Error opening a file with the file extension *.{0}.').format(ext))
            return
    elif os.name == 'posix':
        subprocess.call(('xdg-open', filepath))


def get_all_rasters_from_project(only_postgis: bool = False) -> Dict[str, str]:
    rasters_dict = {}
    all_layers = root.findLayers()
    for layer in all_layers:
        predict_layer = layer.layer()
        if not predict_layer:
            continue
        if only_postgis and predict_layer.isValid() and \
                isinstance(predict_layer, QgsRasterLayer) \
                and predict_layer.dataProvider().name() == 'postgresraster':
            uri = predict_layer.dataProvider().uri()
            rasters_dict[f'{predict_layer.name()}     ||  {uri.schema()}.{uri.table()}'] = predict_layer
        elif not only_postgis and predict_layer.isValid() and \
                isinstance(predict_layer, QgsRasterLayer) and \
                predict_layer.dataProvider().name() == 'gdal':
            rasters_dict[f'{predict_layer.name()}     ||  {predict_layer.id()}'] = predict_layer.source()
    return rasters_dict


def get_all_vectors_from_project(only_postgis: bool = False, wkb: bool = False) \
        -> Dict[str, Tuple[str, int]]:
    vectors_dict = {}
    all_layers = root.findLayers()
    for layer in all_layers:
        predict_layer = layer.layer()
        if not predict_layer:
            continue
        if predict_layer.isValid() and \
                isinstance(predict_layer, QgsVectorLayer):
            if only_postgis and \
                    'postgres' in predict_layer.dataProvider().name():
                name = f'{predict_layer.name()} '
                if wkb:
                    name += f'[{QgsWkbTypes.geometryDisplayString(predict_layer.geometryType())}] '
                name += f'[EPSG:{predict_layer.crs().postgisSrid()}]'
                vectors_dict[name] = predict_layer
            elif not only_postgis and \
                    'postgres' not in predict_layer.dataProvider().name():
                vectors_dict[predict_layer.name()] = \
                    (predict_layer.source(), int(predict_layer.wkbType()))
    return vectors_dict


def standardize_path(path: str) -> str:
    return os.path.normpath(os.sep.join(re.split(r'\\|/', path)))


def get_plugin_object() -> object:
    return qgis.utils.plugins[plugin_dir_name]


def remove_unsupported_chars(input_str: str) -> str:
    temp_str = input_str
    for char in [char for char in
                 '"&<>)¡/\\-{}[]\':>?</*~-,!@#$`%^&*()¢ł¤¥¦§¨©ª«¬­®¯°±²ł´'
                 'µ¶·¸ąº»¼½¾żàáâãäåæçèąćęłńóśźżéęëìíîïðńòóôõö×øùúûüýþßàáâã'
                 'äåæçèéęëìíîïðńòóôõö÷øùúûüýþÿœœššÿˆ˜–—‘’‚“”„†‡‰‹›€™+=|;. ']:
        temp_str = temp_str.replace(char, '')
    return temp_str


def log(message: str, level: int = Qgis.Info) -> None:
    QgsMessageLog.logMessage(message, tag=plugin_name, level=level)


def clean_after_analysis(base_class) -> None:
    if hasattr(base_class, 'temp_dir'):
        shutil.rmtree(base_class.temp_dir, ignore_errors=True)


def fill_item(item, value) -> None:
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


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def qualified_name(schema: str, table: str) -> str:
    return f'{quote_identifier(schema)}.{quote_identifier(table)}'


def postgres_metadata() -> QgsProviderMetadata:
    return QgsProviderRegistry.instance().providerMetadata('postgres')


def get_connection_names() -> List[str]:
    return sorted(postgres_metadata().connections(False).keys())


def create_connection(
        name: str) -> Optional[QgsAbstractDatabaseProviderConnection]:
    try:
        return postgres_metadata().createConnection(name)
    except QgsProviderConnectionException as error:
        log(str(error), Qgis.Critical)
        return None


def create_connection_from_uri(
        uri: str) -> Optional[QgsAbstractDatabaseProviderConnection]:
    try:
        return postgres_metadata().createConnection(uri, {})
    except QgsProviderConnectionException as error:
        log(str(error), Qgis.Critical)
        return None


def connection_for_database(
        connection: QgsAbstractDatabaseProviderConnection,
        database_name: str) -> Optional[QgsAbstractDatabaseProviderConnection]:
    uri = QgsDataSourceUri(connection.uri())
    uri.setDatabase(database_name)
    return create_connection_from_uri(uri.uri(False))


def connection_uri(
        connection: QgsAbstractDatabaseProviderConnection) -> QgsDataSourceUri:
    return QgsDataSourceUri(connection.uri())


def make_query(connection: QgsAbstractDatabaseProviderConnection,
               query: str) -> Optional[list]:
    if not connection:
        return None
    try:
        return connection.executeSql(query)
    except QgsProviderConnectionException as error:
        log(f'{error}\n{query}', Qgis.Critical)
        return None


def check_connection(
        connection: QgsAbstractDatabaseProviderConnection) -> bool:
    return bool(connection) and make_query(connection, 'SELECT 1;') is not None


def get_schema_names(
        connection: QgsAbstractDatabaseProviderConnection) -> List[str]:
    if not connection:
        return []
    try:
        schemas = connection.schemas()
    except QgsProviderConnectionException as error:
        log(str(error), Qgis.Warning)
        return []
    return [schema for schema in schemas if schema not in system_tables]


def get_schema_tables(
        connection: QgsAbstractDatabaseProviderConnection
) -> Dict[str, List[str]]:
    excluded = ', '.join(quote_literal(name) for name in system_tables)
    rows = make_query(connection, f'''
        SELECT n.nspname, c.relname
        FROM pg_namespace n
        LEFT JOIN pg_class c
            ON c.relnamespace = n.oid
            AND c.relkind IN ('r', 'v', 'm', 'p', 'f')
            AND position('_ogr_' IN c.relname) <> 1
        WHERE n.nspname NOT IN ({excluded})
        ORDER BY n.nspname, c.relname;
    ''') or []
    structure = {}
    for schema_name, table_name in rows:
        tables = structure.setdefault(schema_name, [])
        if table_name:
            tables.append(table_name)
    return structure


def get_active_db_info(
        connection: Optional[QgsAbstractDatabaseProviderConnection],
        label: QLabel, simple: bool = False) -> bool:
    active_db_str = tr("Active database:")
    if connection:
        uri = connection_uri(connection)
        db_info = f'{uri.host() or uri.service()}:{uri.port()}, ' \
                  f'{uri.database()}'
        if simple:
            label.setText(f'{active_db_str} {db_info}')
        else:
            label.setText(
                f'{active_db_str} <span style="font-weight:600; '
                f'color:#2ea043;">{db_info}</span>')
        return True
    if simple:
        label.setText(f'{active_db_str} {tr("Not connected.")}')
    else:
        label.setText(
            f'{active_db_str} <span style="font-weight:600; '
            f'color:#e5534b;">{tr("Not connected.")}</span>')
    return False


def create_postgis_raster_layer(
        connection: QgsAbstractDatabaseProviderConnection, schema_name: str,
        table_name: str, raster_name: str,
        rast_column: str = 'rast') -> QgsRasterLayer:
    if "     ||  " in raster_name:
        raster_name = raster_name.split('     ||  ')[0]
    uri = connection_uri(connection)
    uri.setSchema(schema_name)
    uri.setTable(table_name)
    uri.setGeometryColumn(rast_column)
    return QgsRasterLayer(uri.uri(False), raster_name, 'postgresraster')


def create_postgis_vector_layer(
        connection: QgsAbstractDatabaseProviderConnection, schema_name: str,
        table_name: str, geom_col: str = None,
        layer_name: str = '') -> QgsVectorLayer:
    uri = connection_uri(connection)
    uri.setDataSource(schema_name, table_name, geom_col or None)
    return QgsVectorLayer(uri.uri(False), layer_name or table_name, 'postgres')


def invert_dict(input_dict: dict) -> dict:
    return {value: key for key, value in input_dict.items()}


def get_dialog_label_values(dlg_obj: QWidget) -> Any:
    if isinstance(dlg_obj, (QLabel, QPushButton, QToolButton, QCheckBox,
                            QRadioButton)):
        return dlg_obj.text()
    elif not dlg_obj:
        return


def set_dialog_labels(dlg_obj: QWidget, value: str) -> None:
    value = value if value.upper() not in ('NULL', 'NONE') else ''
    if not dlg_obj or not value:
        return
    if isinstance(dlg_obj, (QLabel, QPushButton, QToolButton, QCheckBox,
                            QRadioButton)):
        dlg_obj.setText(value)


class NewThreadAlg:
    def __init__(self, info_dict, func_to_run, progress=False):
        self.info_dict = info_dict
        self.func_to_run = func_to_run
        self.progress = progress

    def start(self) -> None:
        self.msg = iface.messageBar().createMessage(
            self.info_dict['plugin_name'], self.info_dict['alg_name'])
        self.prog = QProgressBar(self.msg)
        if not self.progress:
            self.prog.setMaximum(0)
        self.btn_cancel = QPushButton(self.msg)
        self.btn_cancel.setText(tr('Cancel'))
        self.btn_cancel.clicked.connect(self.cancel)
        self.msg.layout().addWidget(self.prog)
        self.msg.layout().addWidget(self.btn_cancel)
        self.task = self.func_to_run
        self.task.begun.connect(
            lambda: iface.messageBar().pushWidget(self.msg, Qgis.Info))
        self.task.progressChanged.connect(
            lambda: self.prog.setValue(int(self.task.progress())))
        self.task.taskCompleted.connect(self.task_ended_info)
        self.task.taskTerminated.connect(self.task_ended_info)
        QgsApplication.taskManager().addTask(self.task)

    def task_ended_info(self) -> None:
        iface.messageBar().clearWidgets()

    def cancel(self) -> None:
        self.task.cancel()


def delete_item_from_combo(item_name: str, combo: QComboBox) -> None:
    value_idx = combo.findText(item_name)
    if value_idx != -1:
        combo.removeItem(value_idx)
