# -*- coding: utf-8 -*-
from typing import Tuple, Dict, Any

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
from ..utils import get_plugin_object, make_query, test_query, tr, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    get_all_rasters_from_project, \
    create_postgis_raster_layer, add_rasters_to_project, plugin_dir_name


class PostGISToolboxRasterMerge(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'
    OVERVIEWS = 'OVERVIEWS'
    KEEP = 'KEEP'
    OPTIONS = 'OPTIONS'

    def initAlgorithm(self, config=None):
        self.input_raster_layers_dict = get_all_rasters_from_project(True)
        self.input_raster_layers = list(self.input_raster_layers_dict.keys()) \
            if self.input_raster_layers_dict else []
        self.all_layers_dict = {**self.input_raster_layers_dict,
                                **get_all_vectors_from_project(True)}
        self.all_layers_list = list(self.all_layers_dict.keys()) \
            if self.all_layers_dict else []
        if not get_plugin_object().db or not self.input_raster_layers_dict:
            return
        self.db = get_plugin_object().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input raster layer'),
            options=self.input_raster_layers,
            allowMultiple=False,
            defaultValue=self.input_raster_layers[0]))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'merged_raster'))

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
        schema_enum = self.parameterAsEnum(parameters, self.DEST_SCHEMA,
                                           context)
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

            create_raster_table_query, insert_raster_data_query = \
                self.generate_raster_merge_queries(
                    out_table, out_schema, uri_dict
                )

            make_query(self.db, create_raster_table_query)
            make_query(self.db, insert_raster_data_query)
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

    def generate_raster_merge_queries(
            self, out_table: str, out_schema: str,
            uri_dict: Dict[str, Any]) -> Tuple[str, str]:

        create_raster_table = f''' 
            CREATE TABLE "{out_schema}"."{out_table}" (
                rid serial PRIMARY KEY,
                rast raster
            );
        '''
        insert_merged_rasters_data = f'''    
            WITH all_raster AS (
                SELECT ST_UNION("rast") AS merged
                FROM "{uri_dict['SCHEMA']}"."{uri_dict['TABLE']}"
            )
            INSERT INTO "{out_schema}"."{out_table}" ("rast")
            SELECT merged AS rast
            FROM all_raster;
        '''
        return create_raster_table, insert_merged_rasters_data

    def name(self):
        return 'raster_merge_tiles'

    def displayName(self):
        return tr('Merge tiles')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Raster')

    def createInstance(self):
        return PostGISToolboxRasterMerge()
