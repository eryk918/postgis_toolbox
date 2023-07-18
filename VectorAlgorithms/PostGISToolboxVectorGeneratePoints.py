# -*- coding: utf-8 -*-
from typing import Dict, Any, List

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum, QgsProcessingParameterNumber)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection, \
    get_table_geom_columns
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    plugin_dir_name


class PostGISToolboxVectorGeneratePoints(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    POINT_COUNT = 'POINT_COUNT'
    INPUT_SELECT = 'INPUT_SELECT'
    INPUT_MASK_SELECT = 'INPUT_MASK_SELECT'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    SINGLE = 'SINGLE'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'
    KEEP = 'KEEP'
    OPTIONS = 'OPTIONS'

    def initAlgorithm(self, config=None):
        self.input_layers_dict = get_all_vectors_from_project(True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        default_layer = self.input_layers[0] if self.input_layers else None

        if not get_main_plugin_class().db or not self.input_layers_dict:
            return

        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input layers'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=self.input_layers[0]))

        self.addParameter(QgsProcessingParameterNumber(
            name=self.POINT_COUNT,
            description=tr('Number of points'),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=1,
            minValue=1,
            maxValue=99999)
        )

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'points'))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE,
            tr('Overwrite table if exists'),
            True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_TO_PROJECT,
            tr('Add result layer to the project'),
            True))

    def processAlgorithm(self, parameters, context, feedback):
        if not self.input_layers:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('No PostGIS layers in the active project!'),
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}

        input_vector_layer = self.input_layers_dict.get(self.input_layers[self.parameterAsEnum(
            parameters, self.INPUT, context)])
        input_layer_info_dict = {
            'schema_name': get_pg_table_name_from_uri(
                input_vector_layer.dataProvider().dataSourceUri()).split('.')[0],
            'table_name': get_pg_table_name_from_uri(
                input_vector_layer.dataProvider().dataSourceUri()).split('.')[1],
            'srid': input_vector_layer.crs().postgisSrid(),
            'uri': QgsDataSourceUri(input_vector_layer.source()), }
        number_of_points = self.parameterAsInt(
            parameters, self.POINT_COUNT, context)
        q_add_to_project = self.parameterAsBool(
            parameters, self.LOAD_TO_PROJECT, context)
        q_overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)
        schema_enum = self.parameterAsEnum(
            parameters, self.DEST_SCHEMA, context)
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
                if check_table_exists_in_schema(
                        self.db, out_schema, out_table):
                    return {}
            if feedback.isCanceled():
                return {}

            make_query(
                self.db,
                self.generate_points_query(
                    out_table,
                    out_schema,
                    input_layer_info_dict,
                    number_of_points
                )
            )
            create_vector_geom_index(self.db, out_table, 'geom', schema=out_schema)
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'Points',
            geom_col='geom'
        )
        if feedback.isCanceled():
            return {}

        if q_add_to_project:
            add_vectors_to_project(PROCESSING_LAYERS_GROUP, [out_layer])

        return {
            self.OUTPUT: out_layer,
            self.DEST_SCHEMA: schema_enum,
            self.DEST_TABLE: out_table
        }

    def generate_points_query(
            self, out_table: str, out_schema: str,
            input_layer_info_dict: Dict[str, Any],
            number_of_points: int) -> str:

        return f'''
            CREATE TABLE "{out_schema}"."{out_table}" AS (
                SELECT ST_GeneratePoints(ST_Union(
                    "{get_table_geom_columns(self.db, input_layer_info_dict['schema_name'],
                     input_layer_info_dict['table_name'])[0]}"), 
                    {number_of_points}
                ) AS "geom"
                FROM "{input_layer_info_dict['schema_name']}"."{input_layer_info_dict['table_name']}"
            );
        '''

    def name(self):
        return 'vector_generate_points'

    def displayName(self):
        return tr('Generate points')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorGeneratePoints()
