# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict

from plugins.processing.gui.wrappers import WidgetWrapper
from qgis.PyQt.QtWidgets import QMessageBox, QComboBox, QWidget, QVBoxLayout, QSpinBox, QLabel
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterString,
                       QgsProcessingParameterFileDestination)
from qgis.utils import iface

from ..VectorAlgorithms.vec_alg_utils import check_db_connection, \
    get_pg_table_name_from_raster_uri, get_pg_table_name_from_uri
from ..utils import get_plugin_object, make_query, test_query, tr, \
    get_schema_name_list, plugin_name, get_all_rasters_from_project, \
    unpack_nested_lists, plugin_dir_name


class CustomComboSpinBox(WidgetWrapper):
    def createWidget(self):
        editor = QWidget()
        layout = QVBoxLayout()
        self._combo = QComboBox()
        self.input_layers_dict = get_all_rasters_from_project(True)
        self._combo.addItems(list(self.input_layers_dict.keys()) \
                                 if self.input_layers_dict else [])
        self._combo.currentTextChanged.connect(self.limit_band_number)
        self.spinbox = QSpinBox()
        self.spinbox.setMinimum(1)
        layout.addWidget(self._combo)
        layout.addWidget(QLabel(tr('Band number')))
        layout.addWidget(self.spinbox)
        layout.setContentsMargins(0, 0, 0, 0)
        editor.setLayout(layout)
        return editor

    def limit_band_number(self):
        lyr = self.input_layers_dict.get(self._combo.currentText())
        if lyr:
            self.spinbox.setValue(1)
            self.spinbox.setMaximum(lyr.bandCount())

    def value(self):
        return self._combo.currentText(), self.spinbox.value()


class PostGISToolboxRasterSummary(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    SAVE = 'SAVE'

    def initAlgorithm(self, config=None):
        self.input_layers_dict = get_all_rasters_from_project(True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        if not get_plugin_object().db or not self.input_layers_dict:
            return
        self.db = get_plugin_object().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        param = QgsProcessingParameterString(self.INPUT, tr('Input layer'))
        param.setMetadata({
            'widget_wrapper': {
                'class': CustomComboSpinBox}})
        self.addParameter(param)
        self.addParameter(QgsProcessingParameterFileDestination(
            self.SAVE, tr('Output path'), fileFilter='.html'))

    def processAlgorithm(self, parameters, context, feedback):
        if not self.input_layers:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('No PostGIS layers in the active project!'),
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}
        lyr_name, band_numb = parameters.get(self.INPUT)
        input_layer = self.input_layers_dict.get(lyr_name)
        uri_dict = get_pg_table_name_from_raster_uri(
            input_layer.dataProvider().dataSourceUri())
        if not uri_dict.get('TABLE'):
            schema_name, table_name = get_pg_table_name_from_uri(
                input_layer.dataProvider().dataSourceUri()).split('.')
            if schema_name and table_name:
                uri_dict = {
                    'TABLE': table_name,
                    'SCHEMA': schema_name
                }
        if not uri_dict.get('TABLE'):
            return {}

        file_output = self.parameterAsFileOutput(parameters, self.SAVE, context)
        result_path = ''
        if feedback.isCanceled():
            return {}
        if self.db.isOpen() and self.db.isValid() \
                and make_query(self.db, test_query):
            result_statistics = unpack_nested_lists(make_query(
                self.db,
                self.generate_raster_statistics_query(uri_dict, band_numb)
            ))
            if result_statistics:
                file_handle, path_to_temp_file = tempfile.mkstemp(
                    suffix='_statistics_tmp.html')
                os.close(file_handle)
                _, sum_count, mean, stddev, min_value, max_value = result_statistics

                file_analyzed, database, schema, table, minimum_value, \
                maximum_value, range_value, sum_value, average_value, \
                standard_deviation = \
                    tr('File analyzed'), tr('database'), tr('schema'), \
                    tr('table'), tr('Minimum value'), tr('Maximum value'), \
                    tr('Range'), tr('Sum'), tr('Mean value'), \
                    tr('Standard deviation')

                html = f'''<h3><b>{file_analyzed}</b>: {database} <i>"{self.db.databaseName()}"</i>, 
                            {schema} <i>"{uri_dict.get('SCHEMA')}"</i>, {table} <i>"{uri_dict.get('TABLE')}"</i></h3>
                        <p>{minimum_value}: {min_value},</p>
                        <p>{maximum_value}: {max_value},</p>
                        <p>{range_value}: {max_value - min_value},</p>
                        <p>{sum_value}: {sum_count},</p>
                        <p>{average_value}: {mean},</p>
                        <p>{standard_deviation}: {stddev}.</p>'''
                html_file = open(path_to_temp_file, 'w')
                html_file.write(html)
                html_file.close()
                result_path = path_to_temp_file
                if not os.path.splitext(file_output)[-1] == 'file':
                    shutil.copy(path_to_temp_file, file_output)
                    result_path = path_to_temp_file
                if sys.platform.startswith('darwin'):
                    subprocess.call(('open', result_path))
                elif os.name in ('nt', 'posix'):
                    try:
                        if os.name == 'nt':
                            os.startfile(result_path)
                        else:
                            subprocess.call(('xdg-open', result_path))
                    except OSError:
                        QMessageBox.critical(
                            iface.mainWindow(), plugin_name,
                            tr('There was a problem with opening a file.'),
                            QMessageBox.Ok)
        return {'OUTPUT': result_path}

    def generate_raster_statistics_query(
            self, uri_dict: Dict[str, Any],
            band_numb: int) -> str:

        return f'''
            WITH union_raster AS (
                SELECT ST_UNION("rast", {band_numb}) AS rast_union 
                FROM "{uri_dict.get('SCHEMA')}"."{uri_dict.get('TABLE')}"
            )
            SELECT (stats).*
            FROM (
                SELECT ST_SummaryStats(
                    rast_union, 
                    {band_numb}
                ) AS stats 
                FROM union_raster
            ) AS temp;
        '''

    def name(self):
        return 'raster_summary'

    def displayName(self):
        return tr('Summary')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Raster')

    def createInstance(self):
        return PostGISToolboxRasterSummary()
