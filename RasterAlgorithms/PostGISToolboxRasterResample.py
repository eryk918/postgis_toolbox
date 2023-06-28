# -*- coding: utf-8 -*-
from typing import Dict, Any

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterNumber)
from qgis.utils import iface

from ..ImportRaster.utils.raster_utils import make_sql_create_raster_gist, \
    make_sql_addr_raster_column, create_raster_overviews
from ..VectorAlgorithms.vec_alg_utils import check_db_connection, \
    get_pg_table_name_from_raster_uri, check_table_exists_in_schema, \
    get_pg_table_name_from_uri
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    get_all_rasters_from_project, \
    create_postgis_raster_layer, add_rasters_to_project


class PostGISToolboxRasterResample(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    ALG_NAME = 'ALG_NAME'
    MAX_ERR = 'MAX_ERR'
    SCALE_VALUE = 'SCALE_VALUE'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'
    OVERVIEWS = 'OVERVIEWS'
    KEEP = 'KEEP'
    OPTIONS = 'OPTIONS'

    def initAlgorithm(self, config=None):
        self.alg_names_list = ['NearestNeighbor', 'Bilinear', 'Cubic',
                               'CubicSpline', 'Lanczos']
        self.input_raster_layers_dict = get_all_rasters_from_project(True)
        self.input_raster_layers = list(self.input_raster_layers_dict.keys()) \
            if self.input_raster_layers_dict else []
        self.all_layers_dict = {**self.input_raster_layers_dict,
                                **get_all_vectors_from_project(True)}
        self.all_layers_list = list(self.all_layers_dict.keys()) \
            if self.all_layers_dict else []
        if not get_main_plugin_class().db or not self.input_raster_layers_dict:
            return
        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input raster layer'),
            options=self.input_raster_layers,
            allowMultiple=False,
            defaultValue=self.input_raster_layers[0]))

        self.addParameter(QgsProcessingParameterNumber(
            self.SCALE_VALUE,
            tr("Spatial resolution"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=100,
            minValue=0.0000001,
            maxValue=99999999
        ))

        self.addParameter(QgsProcessingParameterEnum(
            self.ALG_NAME,
            tr("Resampling algorithm"),
            options=self.alg_names_list,
            defaultValue=self.alg_names_list[0],
            allowMultiple=False))

        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_ERR,
            tr("Maximum percentage error"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.125,
            minValue=0,
            maxValue=100
        ))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'resampled_raster'))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE,
            tr('Overwrite table if exists'),
            True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERVIEWS,
            tr('Create raster overviews'),
            True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_TO_PROJECT,
            tr('Add result layer to the project'),
            True))

    def processAlgorithm(self, parameters, context, feedback):
        if not self.input_raster_layers:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('No PostGIS layers in the active project!'),
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}

        raster_layer_name = self.input_raster_layers[self.parameterAsEnum(
            parameters, self.INPUT, context)]
        raster_layer = self.input_raster_layers_dict[raster_layer_name]
        uri_dict = get_pg_table_name_from_raster_uri(
            raster_layer.dataProvider().dataSourceUri())

        if not uri_dict.get('TABLE'):
            schema_name, table_name = get_pg_table_name_from_uri(
                raster_layer.dataProvider().dataSourceUri()).split('.')
            if schema_name and table_name:
                uri_dict = {
                    'TABLE': table_name,
                    'SCHEMA': schema_name
                }
        if not uri_dict.get('TABLE'):
            return {}

        q_add_to_project = self.parameterAsBool(
            parameters, self.LOAD_TO_PROJECT, context)
        q_overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)
        q_overview = self.parameterAsBool(parameters, self.OVERVIEWS, context)
        schema_enum = self.parameterAsEnum(
            parameters, self.DEST_SCHEMA, context)
        resampling_algorithm = self.parameterAsString(
            parameters, self.ALG_NAME, context)
        scale_value = self.parameterAsDouble(
            parameters, self.SCALE_VALUE, context)
        resampling_error = self.parameterAsDouble(
            parameters, self.MAX_ERR, context)
        out_schema = self.schemas_list[schema_enum]
        out_table = remove_unsupported_chars(
            self.parameterAsString(parameters, self.DEST_TABLE, context))
        if feedback.isCanceled():
            return {}

        if self.db.isOpen() and self.db.isValid() \
                and make_query(self.db, test_query):
            if q_overwrite:
                make_query(self.db, f'DROP TABLE IF EXISTS '
                                    f'"{out_schema}"."{out_table}";')
            else:
                if check_table_exists_in_schema(self.db, out_schema,
                                                out_table):
                    return {}
            if feedback.isCanceled():
                return {}

            make_query(
                self.db,
                self.generate_raster_resample_query(
                    out_table, out_schema,
                    uri_dict, resampling_algorithm,
                    scale_value, resampling_error
                )
            )

            make_query(self.db, make_sql_create_raster_gist(out_table, out_table),
                       out_schema)
            make_query(self.db,
                       make_sql_addr_raster_column(out_table, out_schema))
            if q_overview:
                create_raster_overviews(self.db, out_schema, out_table)
            if feedback.isCanceled():
                make_query(self.db, f'DROP TABLE IF EXISTS '
                                    f'"{out_schema}"."{out_table}";')
                return {}

        out_layer = create_postgis_raster_layer(
            self.db, out_schema, out_table, raster_layer_name
        )

        if feedback.isCanceled():
            return {}

        if q_add_to_project:
            add_rasters_to_project(PROCESSING_LAYERS_GROUP, [out_layer],
                                   postgis_raster=True)

        return {
            self.OUTPUT: out_layer,
            self.DEST_SCHEMA: schema_enum,
            self.DEST_TABLE: out_table
        }

    def generate_raster_resample_query(
            self, out_table: str, out_schema: str,
            uri_dict: Dict[str, Any], resampling_algorithm: str,
            scale_value: float, resampling_error: float) -> str:

        return f''' 
            CREATE TABLE "{out_schema}"."{out_table}" AS (
                SELECT "rid", 
                    ST_Rescale(
                        "rast", 
                        {scale_value}, 
                        '{resampling_algorithm}', 
                        {resampling_error}
                    ) AS "rast"
                FROM "{uri_dict.get('SCHEMA')}"."{uri_dict.get('TABLE')}"
            );
        '''

    def name(self):
        return 'raster_resample'

    def displayName(self):
        return tr('Resample')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Raster')

    def createInstance(self):
        return PostGISToolboxRasterResample()
