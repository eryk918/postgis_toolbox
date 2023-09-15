# -*- coding: utf-8 -*-
from typing import Any, Dict

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum,
                       QgsWkbTypes, QgsProcessingParameterNumber)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection, \
    get_table_geom_columns
from ..utils import get_plugin_object, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name


class PostGISToolboxVectorGeneratePolygonFromPoints(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    ALLOW_HOLES = 'ALLOW_HOLES'
    CONCAVITY_RATIO = 'CONCAVITY_RATIO'
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
        self.input_layers_dict = {key: value for key, value in self.input_layers_dict.items()
                                  if QgsWkbTypes.geometryDisplayString(QgsWkbTypes.geometryType(value.wkbType())) in ('Point', 'MultiPoint')}
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        default_layer = self.input_layers[0] if self.input_layers else None

        if not get_plugin_object().db or not self.input_layers_dict:
            return

        self.db = get_plugin_object().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input point layer'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=default_layer))

        self.addParameter(QgsProcessingParameterNumber(
            self.CONCAVITY_RATIO,
            tr('Concavity ratio'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.4,
            minValue=0,
            maxValue=1
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.ALLOW_HOLES,
            tr('Allow holes?'),
            True))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_layer))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'polygon_from_points'))

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
        concavity_ratio = self.parameterAsDouble(
            parameters, self.CONCAVITY_RATIO, context)
        allow_holes = self.parameterAsBool(
            parameters, self.ALLOW_HOLES, context)
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
                self.generate_polygons_by_points_query(
                    out_table,
                    out_schema,
                    input_layer_info_dict,
                    concavity_ratio,
                    allow_holes
                )
            )
            create_vector_geom_index(
                self.db, out_table, 'geom', schema=out_schema)
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'Polygon from points',
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

    def generate_polygons_by_points_query(
            self, out_table: str, out_schema: str,
            input_layer_info_dict: Dict[str, Any],
            concavity_ratio: float, allow_holes: bool) -> str:

        return f'''
            CREATE TABLE "{out_schema}"."{out_table}" AS (
                SELECT ST_ConcaveHull(
                    ST_Union(
                        "{get_table_geom_columns(self.db, input_layer_info_dict['schema_name'],
                         input_layer_info_dict['table_name'])[0]}"), 
                         {concavity_ratio}, 
                         {allow_holes}
                    ) AS "geom"
                FROM "{input_layer_info_dict['schema_name']}"."{input_layer_info_dict['table_name']}"
            );
        '''

    def name(self):
        return 'generate polygon from points'

    def displayName(self):
        return tr('Generate polygon from points')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorGeneratePolygonFromPoints()
