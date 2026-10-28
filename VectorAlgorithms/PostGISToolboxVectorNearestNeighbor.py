# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterBoolean, \
    QgsProcessingParameterNumber, QgsProcessing

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorNearestNeighbor(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    INPUT_NEIGHBOR = 'INPUT_NEIGHBOR'
    FIELDS = 'FIELDS'
    MIN_DISTANCE = 'MIN_DISTANCE'
    MAX_DISTANCE = 'MAX_DISTANCE'
    SINGLE = 'SINGLE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer:')))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_NEIGHBOR, tr('Neighbor layer: [point layer]'),
            types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_DISTANCE, tr('Minimum distance:'),
            type=QgsProcessingParameterNumber.Double, defaultValue=None,
            optional=True, minValue=0, maxValue=99999))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_DISTANCE, tr('Maximum distance:'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0,
            minValue=0, maxValue=99999))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))
        self.add_connection_parameter()
        self.add_output_parameters('neighbor')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        neighbor_layer = self.get_postgis_layer(
            parameters, self.INPUT_NEIGHBOR, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        neighbor_schema, neighbor_table, neighbor_geom_column = \
            self.layer_table(neighbor_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        min_distance = self.parameterAsDouble(
            parameters, self.MIN_DISTANCE, context) \
            if parameters.get(self.MIN_DISTANCE) is not None else None
        max_distance = self.parameterAsDouble(
            parameters, self.MAX_DISTANCE, context)
        single = self.parameterAsBool(parameters, self.SINGLE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_nearest_neighbor_query(
            out_schema, out_table, schema, table, geom_column, columns,
            neighbor_schema, neighbor_table, neighbor_geom_column,
            input_layer.crs().postgisSrid(),
            neighbor_layer.crs().postgisSrid(),
            self.output_geometry_type(input_layer, single), single,
            min_distance, max_distance), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("NearestNeighbor")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_nearest_neighbor_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str], neighbor_schema: str,
            neighbor_table: str, neighbor_geom_column: str, srid: int,
            neighbor_srid: int, out_geom_type: str, single: bool,
            min_distance: float, max_distance: float) -> str:
        input_geom = f'g1.{quote_identifier(geom_column)}'
        neighbor_geom = f'{quote_identifier(neighbor_table)}.' \
                        f'{quote_identifier(neighbor_geom_column)}'
        if neighbor_srid != srid:
            neighbor_geom = f'ST_Transform({neighbor_geom}, {srid})'
        geom_part = f'{input_geom} AS "geom"'
        if single:
            geom_part = f'(ST_Dump({input_geom})).geom::geometry(' \
                        f'{out_geom_type}, {srid}) AS "geom"'
        distance = f'{neighbor_geom} <-> {input_geom}'
        if min_distance:
            condition = f'{distance} >= {min_distance} AND ' \
                        f'{distance} <= {max_distance}'
        else:
            condition = f'ST_Within({neighbor_geom}, {input_geom}) OR ' \
                        f'{distance} <= {max_distance}'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('g1', columns)}{geom_part}
                FROM {qualified_name(schema, table)} AS g1
                CROSS JOIN LATERAL (
                    SELECT {distance} AS dist
                    FROM {qualified_name(neighbor_schema, neighbor_table)}
                    WHERE {condition}
                    ORDER BY dist
                ) g2
            );
        '''

    def name(self):
        return 'vector_nearest_neighbor'

    def displayName(self):
        return tr('Nearest Neighbor')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorNearestNeighbor()
