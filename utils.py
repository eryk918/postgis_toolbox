# -*- coding: utf-8 -*-

import os
import os.path
import re
import shutil
import subprocess
import sys
from datetime import datetime
from typing import List, Tuple, Any, Dict

import qgis
from PyQt5.QtCore import Qt
from chardet import detect
from qgis.PyQt.QtCore import QCoreApplication, NULL, QTimer, \
    QSortFilterProxyModel, QItemSelectionModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtSql import QSqlDatabase
from qgis.PyQt.QtSql import QSqlQuery
from qgis.PyQt.QtWidgets import QComboBox, QProgressBar, QTreeWidgetItem, \
    QDialog, QLineEdit, QRadioButton, QToolButton, QCheckBox, QFrame, \
    QGroupBox, QWidget
from qgis.PyQt.QtWidgets import QProgressDialog, QPushButton, QMessageBox, \
    QApplication, QLabel
from qgis.core import QgsMessageLog, Qgis, QgsDataSourceUri, \
    QgsWkbTypes, QgsAuthMethodConfig, QgsProviderRegistry, QgsTask
from qgis.core import QgsProject, QgsVectorLayer, \
    QgsRasterLayer, QgsApplication, QgsMapLayerType
from qgis.utils import iface

project = QgsProject.instance()
root = project.layerTreeRoot()
main_window = iface.mainWindow()

plugin_name = 'PostGIS Toolbox'
plugin_dir = os.path.dirname(__file__)
plugin_dir_name = 'postgis_toolbox'
main_plugin_icon = QIcon(os.path.join(plugin_dir, 'icons', 'main.png'))

connection_key_names = [
    'authcfg', 'database', 'host', 'password', 'port', 'service',
    'sslmode', 'username', 'connection_name'
]

system_tables = ['pg_catalog', 'pg_toast_temp_1', 'pg_temp_1', 'pg_toast',
                 'information_schema', 'public', 'topology']

conn_key_string = '/PostgreSQL/connections/'

test_query = 'SELECT version();'


def tr(text: str):
    return QCoreApplication.translate('@default', text)


PROCESSING_LAYERS_GROUP = tr('PROCESSING_LAYERS')
RASTERS_LAYERS_GROUP = tr("IMPORTED RASTERS")
VECTORS_LAYERS_GROUP = tr("IMPORTED VECTORS")


class CreateTemporaryLayer(QgsVectorLayer):
    parent_layer = None

    def __init__(self, *args, **kwargs):
        super(CreateTemporaryLayer, self).__init__(*args, **kwargs)

    def set_layer_fields(self, fields):
        self.dataProvider().addAttributes(fields)
        self.updateFields()


def repair_dialog(dlg: QDialog, icon_file: str = None,
                  translate_dialog: bool = True) -> None:
    obj_types = [QLabel, QLineEdit, QRadioButton, QToolButton, QCheckBox,
                 QGroupBox, QFrame]
    dialog_obj_list = [dlg.__getattribute__(obj) for obj in dlg.__dir__()]
    objs_to_repair = [elem for obj_list in
                      [dlg.findChildren(obj) for obj in obj_types]
                      for elem in obj_list]

    if translate_dialog:
        for obj in dialog_obj_list:
            data = get_dialog_label_values(obj)
            if not data:
                continue
            set_dialog_labels(obj, tr(data))

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
    for dlg_obj in objs_to_repair:
        if dlg_obj.objectName() != 'title_frame':
            dlg_obj.setStyleSheet(
                dlg_obj.styleSheet() +
                ''' QLabel, QLineEdit, QRadioButton, QToolButton, 
                QFrame, QCheckBox, QGroupBox{background-color: 0;}''')
    if icon_file:
        dlg.setWindowIcon(QIcon(os.path.join(plugin_dir, 'icons', icon_file)))
    else:
        dlg.setWindowIcon(main_plugin_icon)


def get_project_setting(parameter, key, default=''):
    return project.readEntry(parameter, key, default)[0]


def set_project_setting(parameter, key, value):
    return project.writeEntry(parameter, key, value)


def create_progress_bar(max_len, title=tr('Please wait'),
                        txt=tr('Data is being processed...'), start_val=0,
                        auto_close=True, cancel_btn=None, silent=False):
    progress_bar = QProgressDialog()
    progress_bar.setFixedWidth(500)
    progress_bar.setWindowTitle(f"{plugin_name} - {title}")
    progress_bar.setWindowIcon(main_plugin_icon)
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


def create_postgis_raster_layer(db: QSqlDatabase, schema_name: str,
                                table_name: str, raster_name: str,
                                rast_column: str = 'rast') -> QgsRasterLayer:
    if "     ||  " in raster_name:
        raster_name = raster_name.split('     ||  ')[0]

    uri_config = {
        'dbname': db.databaseName(),
        'host': db.hostName(),
        'port': db.port(),
        'sslmode': QgsDataSourceUri.SslDisable,
        'authcfg': 'QconfigId',
        'username': db.userName(),
        'password': db.password(),
        'schema': schema_name,
        'table': table_name,
        'geometrycolumn': rast_column,
        'estimatedmetadata': 'False',
        'mode': '2',
    }
    meta = QgsProviderRegistry.instance().providerMetadata('postgresraster')
    uri = QgsDataSourceUri(meta.encodeUri(uri_config))
    return QgsRasterLayer(uri.uri(False), raster_name, "postgresraster")


def create_postgis_vector_layer(
        db, schema_name, table_name,
        geom_col=None, layer_name='', ignore_validation=False):
    uri = QgsDataSourceUri()
    uri.setConnection(db.hostName(), str(db.port()), db.databaseName(),
                      db.userName(), db.password())
    if geom_col:
        uri.setDataSource(schema_name, table_name, geom_col)
    else:
        uri.setSchema(schema_name)
        uri.setTable(table_name)

    vlayer = QgsVectorLayer(uri.uri(), layer_name or table_name, "postgres")
    if ignore_validation:
        if vlayer.isValid():
            return vlayer
    else:
        return vlayer


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
            QMessageBox.critical(
                None, plugin_name,
                f'''Error opening a file with the file extension *.{ext}.''',
                QMessageBox.Ok)
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
                predict_layer.type() == QgsMapLayerType.RasterLayer \
                and predict_layer.dataProvider().name() == 'postgresraster':
            uri = predict_layer.dataProvider().uri()
            rasters_dict[f'{predict_layer.name()}     ||  {uri.schema()}.{uri.table()}'] = predict_layer
        elif not only_postgis and predict_layer.isValid() and \
                predict_layer.type() == QgsMapLayerType.RasterLayer and \
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
                predict_layer.type() == QgsMapLayerType.VectorLayer:
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
                    (predict_layer.source(), predict_layer.wkbType())
    return vectors_dict


def standardize_path(path: str) -> str:
    return os.path.normpath(os.sep.join(re.split(r'\\|/', path)))


def get_main_plugin_class() -> object:
    return qgis.utils.plugins[plugin_dir_name]


def repair_encoding(tmp_dir: str, infile: str) -> None:
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


def repair_path_for_exec(string: str) -> str:
    return string.replace('\\', '\\\\')


def remove_unsupported_chars(input_str: str) -> str:
    temp_str = input_str
    for char in [char for char in
                 '"&<>)¡/\-{}[]\':>?</*~-,!@#$`%^&*()¢ł¤¥¦§¨©ª«¬­®¯°±²ł´' \
                 'µ¶·¸ąº»¼½¾żàáâãäåæçèąćęłńóśźżéęëìíîïðńòóôõö×øùúûüýþßàáâã' \
                 'äåæçèéęëìíîïðńòóôõö÷øùúûüýþÿœœššÿˆ˜–—‘’‚“”„†‡‰‹›€™+=|;. ']:
        temp_str = temp_str.replace(char, '')
    return temp_str


def throw_log_message(mess: str) -> None:
    QgsMessageLog.logMessage(mess, tag=plugin_name)


def clean_after_analysis(base_class) -> None:
    QApplication.processEvents()
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


def get_all_tables_from_schema(db: QSqlDatabase, schema_name: str) -> List:
    tables_list = make_query(db, f'''
        SELECT "table_name" 
        FROM information_schema.tables 
        WHERE table_schema = '{schema_name}' AND table_name NOT IN 
            ('_ogr_other_metadata', '_ogr_fields_metadata', 
            '_ogr_layers_metadata', '_ogr_layer_relationships');
    ''')
    return list(list(zip(*tables_list))[0]) if tables_list else []


def get_schema_name_list(db: QSqlDatabase, db_name: str = '',
                         change_db: bool = True) -> Tuple[list, QSqlDatabase]:
    if change_db:
        db.setDatabaseName(db_name)
        db.open()
    if db.isOpen() and db.isValid() and make_query(db, test_query):
        schema_names_result = make_query(db, f'''
            SELECT schema_name 
            FROM information_schema.schemata
            WHERE schema_name NOT IN 
                ({','.join(f"'{name}'" for name in system_tables)});
        ''')
        list_to_cbbx = list(zip(*schema_names_result))[
            0] if schema_names_result else []
        return list(list_to_cbbx), db
    else:
        return [], db


def get_active_db_info(db: QSqlDatabase or None, label: QLabel,
                       simple: bool = False) -> bool:
    active_db_str = tr("Active database:")
    if db and db.isOpen() and db.isValid():
        db_hostname = db.hostName()
        db_port = db.port()
        db_database_name = db.databaseName()
        if simple:
            label.setText(
                f'{active_db_str} {db_hostname}:{db_port}, '
                f'{db_database_name}')
        else:
            label.setText(
                f'{active_db_str} <span style=" font-size:9pt; '
                f'font-weight:600; color:#32CD32;">{db_hostname}:{db_port}, '
                f'{db_database_name}</span>')
        return True
    else:
        if simple:
            label.setText(f'{active_db_str} {tr("Not connected.")}')
        else:
            label.setText(
                f'{active_db_str} <span style=" font-size:9pt; '
                f'font-weight:600; color:#aa0000;">{tr("Not connected.")}</span>')
        return False


def create_pg_connecton(db_params: dict) -> QSqlDatabase:
    pg_connection = QSqlDatabase.addDatabase('QPSQL', db_params['connection_name'])
    QApplication.processEvents()
    pg_connection.setHostName(db_params['host'])
    pg_connection.setDatabaseName(db_params['database'])
    pg_connection.setPort(int(db_params['port']))
    if db_params.get('authcfg'):
        conf = QgsAuthMethodConfig()
        auth_manager = QgsApplication.authManager()
        auth_manager.loadAuthenticationConfig(db_params['authcfg'], conf, True)
        pg_connection.setUserName(conf.config('username', ''))
        pg_connection.setPassword(conf.config('password', ''))
    else:
        if db_params.get('username') and db_params.get('password'):
            pg_connection.setUserName(db_params['username'])
            pg_connection.setPassword(db_params['password'])
    pg_connection.open()
    return pg_connection


def make_query(db: QSqlDatabase, query: str, schema_name: str = '',
               prepare: Any = None, postgis_raster: bool = False) -> list:
    response = []
    if not db.isOpen():
        db.open()
    query_obj = QSqlQuery(db)
    if schema_name:
        query_obj.exec_(f'SET search_path TO "{schema_name}",public;')
    if postgis_raster:
        query_obj.exec_('''SET postgis.gdal_enabled_drivers = 'ENABLE_ALL';''')
    if prepare is not None:
        query_obj.prepare(query)
        query_obj.addBindValue(prepare)
    request = query_obj.exec_(query) if prepare is None else query_obj.exec()
    if request:
        object_amount = query_obj.record().count()
        while query_obj.next():
            row = []
            for object_id in range(0, object_amount):
                val = query_obj.value(object_id)
                row.append(None if val == NULL else val)
            response.append(row)
    else:
        response = [query_obj.lastError().databaseText()]
    return response


def make_queries(db: QSqlDatabase, sql_list: List[str] or List[str, Any],
                 schema_name: str = '', postgis_raster: bool = False,
                 prepare: bool = False, base_class=None,
                 percent_amount: int = None) -> bool:
    query = QSqlQuery(db)
    if db.driverName() == "QPSQL":
        query.exec_(f"SET search_path TO {schema_name},public;")
    query.exec_('BEGIN;')
    if postgis_raster:
        query.exec_('''SET postgis.gdal_enabled_drivers = 'ENABLE_ALL';''')
    for exp in sql_list:
        if prepare:
            query.prepare(exp[0])
            query.addBindValue((exp[1]))
            query.exec()
        else:
            query.exec_(exp)
        if base_class and hasattr(base_class, 'cancel_detection'):
            if base_class.cancel_detection():
                return False
        if base_class and hasattr(base_class, 'last_progress_value'):
            base_class.last_progress_value = \
                change_alg_progress(base_class, base_class.last_progress_value,
                                    percent_amount / len(sql_list))

    query.exec_('COMMIT;')
    return True


def unpack_nested_lists(n_list: List[List[Any]]) -> List[Any] or str:
    return [elem for nested_list in n_list for elem in nested_list
            if not isinstance(nested_list, str)]


def universal_db_check(db: QSqlDatabase) -> bool:
    return True if db and db.isOpen() and db.isValid() and \
                   make_query(db, test_query) else False


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
            lambda: self.prog.setValue(self.task.progress()))
        self.task.taskCompleted.connect(lambda: self.task_ended_info())
        self.task.taskTerminated.connect(lambda: self.task_ended_info(False))
        QgsApplication.taskManager().addTask(self.task)

    def task_ended_info(self, successfully: bool = True) -> None:
        iface.messageBar().clearWidgets()
        self.task.finished(True) if successfully \
            else self.task.finished('canceled')
        del self.task

    def cancel(self) -> None:
        self.task.cancel()


def delete_item_from_combo(item_name: str, combo: QComboBox) -> None:
    value_idx = combo.findText(item_name)
    if value_idx != -1:
        combo.removeItem(value_idx)
