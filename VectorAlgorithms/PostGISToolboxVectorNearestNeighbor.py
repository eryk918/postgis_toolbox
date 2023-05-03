# -*- coding: utf-8 -*-

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum, QgsWkbTypes,
                       QgsProcessingParameterNumber)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection, get_table_columns, \
    get_table_geom_columns
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    plugin_dir_name


class PostGISToolboxVectorNearestNeighbor(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    INPUT_NEIGHBOR = 'INPUT_NEIGHBOR'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    SINGLE = 'SINGLE'
    MIN_DISTANCE = 'MIN_DISTANCE'
    MAX_DISTANCE = 'MAX_DISTANCE'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'
    KEEP = 'KEEP'
    OPTIONS = 'OPTIONS'

    def initAlgorithm(self, config=None):
        self.input_layers_dict = get_all_vectors_from_project(True, True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        default_layer = self.input_layers[-1] if self.input_layers else None

        if not get_main_plugin_class().db or not self.input_layers_dict \
                or not default_layer:
            return

        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input layer:'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=self.input_layers[0]))

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT_NEIGHBOR,
            tr('Neighbor layer: [point layer]'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=default_layer))

        self.addParameter(QgsProcessingParameterNumber(
            name=self.MIN_DISTANCE,
            description=tr('Minimum distance:'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=None,
            optional=True,
            minValue=0,
            maxValue=99999)
        )

        self.addParameter(QgsProcessingParameterNumber(
            name=self.MAX_DISTANCE,
            description=tr('Maximum distance:'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0,
            optional=False,
            minValue=0,
            maxValue=99999)
        )

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name:'), 'neighbor'))

        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE,
            tr('Overwrite table if exists'),
            True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_TO_PROJECT,
            tr('Add result layer to the project'),
            True))

    def processAlgorithm(self, parameters, context, feedback):
        if not hasattr(self, 'input_layers') or not self.input_layers:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('No PostGIS layers in the active project!'),
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}

        min_distance = self.parameterAsDouble(
            parameters, self.MIN_DISTANCE, context)
        max_distance = self.parameterAsDouble(
            parameters, self.MAX_DISTANCE, context)

        input_layer_a = self.input_layers_dict[
            self.input_layers[self.parameterAsEnum(
                parameters, self.INPUT, context)]]
        schema_name_a, table_name_a = get_pg_table_name_from_uri(
            input_layer_a.dataProvider().dataSourceUri()).split('.')
        layer_name = input_layer_a.name()
        srid_a = input_layer_a.crs().postgisSrid()
        uri_a = QgsDataSourceUri(input_layer_a.source())
        geom_col_a = uri_a.geometryColumn()
        geom_type_a = input_layer_a.geometryType()

        input_layer_b = self.input_layers_dict[
            self.input_layers[self.parameterAsEnum(
                parameters, self.INPUT_NEIGHBOR, context)]]
        schema_name_b, table_name_b = get_pg_table_name_from_uri(
            input_layer_b.dataProvider().dataSourceUri()).split('.')
        uri_b = QgsDataSourceUri(input_layer_b.source())
        geom_col_b = uri_b.geometryColumn()
        srid_b = input_layer_b.crs().postgisSrid()

        q_single_type = self.parameterAsBool(parameters, self.SINGLE, context)
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

        if geom_type_a == QgsWkbTypes.PointGeometry:
            out_geom_type = "POINT"
        elif geom_type_a == QgsWkbTypes.LineGeometry:
            out_geom_type = "LINESTRING"
        else:
            out_geom_type = "POLYGON"

        if not q_single_type:
            out_geom_type = f"MULTI{out_geom_type}"

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

            columns = get_table_columns(
                self.db,
                schema_name_a,
                table_name_a,
                get_table_geom_columns(
                    self.db,
                    schema_name_a,
                    table_name_a
                )
            )

            if feedback.isCanceled():
                return {}

            geom_part_a = f'g1."{geom_col_a}"'
            geom_part_b = f'"{table_name_b}"."{geom_col_b}"'

            if srid_a != srid_b:
                geom_part_b = f'ST_Transform({geom_part_b}, {srid_a})'

            geom_query_part = f'{geom_part_a} AS geom'
            if q_single_type:
                geom_query_part = f'(ST_Dump({geom_part_a})).geom::geometry(' \
                                  f'{out_geom_type}, {srid_a}) AS geom'

            condition = ''
            if min_distance:
                condition += f'{geom_part_b} <-> {geom_part_a} >= ' \
                             f'{min_distance} AND'
            else:
                condition += f'ST_Within({geom_part_b}, {geom_part_a}) OR '
            condition += f'{geom_part_b} <-> {geom_part_a} <= {max_distance}'

            query = f'''
                CREATE TABLE "{out_schema}"."{out_table}" AS(
                    SELECT g1."{f'", g1."'.join(columns)}", {geom_query_part}
                       FROM "{schema_name_a}"."{table_name_a}" AS g1
                       CROSS JOIN LATERAL (
                           SELECT {geom_part_b} <-> {geom_part_a} AS dist
                           FROM "{schema_name_b}"."{table_name_b}"
                           WHERE {condition}
                           ORDER BY dist
                       ) g2
                );
            '''
            make_query(self.db, query)
            create_vector_geom_index(self.db, out_table, 'geom')
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'{tr("NearestNeighbor")} {layer_name}',
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

    def name(self):
        return 'vector_nearest_neighbor'

    def displayName(self):
        return tr('Nearest Neighbor')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorNearestNeighbor()
