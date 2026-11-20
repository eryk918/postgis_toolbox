# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterBoolean, \
    QgsProcessingParameterNumber, QgsProcessing, QgsVectorLayer

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorNearestNeighbor(PostGISToolboxAlgorithm):
    HELP_PAGE = 'geometry_distance_knn'
    INPUT = 'INPUT'
    INPUT_NEIGHBOR = 'INPUT_NEIGHBOR'
    FIELDS = 'FIELDS'
    MIN_DISTANCE = 'MIN_DISTANCE'
    MAX_DISTANCE = 'MAX_DISTANCE'
    SINGLE = 'SINGLE'
    NEIGHBOR_ID = 'NEIGHBOR_ID'
    NEIGHBOR_COUNT = 'NEIGHBOR_COUNT'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_NEIGHBOR, tr('Neighbor layer: [point layer]'),
            types=[QgsProcessing.SourceType.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterField(
            self.NEIGHBOR_ID, tr('Neighbor identifier column'),
            parentLayerParameterName=self.INPUT_NEIGHBOR, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.NEIGHBOR_COUNT, tr('Number of neighbors'),
            type=QgsProcessingParameterNumber.Type.Integer, defaultValue=1,
            minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_DISTANCE, tr('Minimum distance'),
            type=QgsProcessingParameterNumber.Type.Double, defaultValue=None,
            optional=True, minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_DISTANCE, tr('Maximum distance'),
            type=QgsProcessingParameterNumber.Type.Double, defaultValue=0,
            minValue=0))
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
        source, geom_column = self.input_source(input_layer)
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
        neighbor_count = self.parameterAsInt(
            parameters, self.NEIGHBOR_COUNT, context)
        neighbor_id = self.neighbor_id_column(
            parameters, context, neighbor_layer)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_nearest_neighbor_query(
            out_schema, out_table, source, geom_column, columns,
            neighbor_schema, neighbor_table, neighbor_geom_column,
            input_layer.crs().postgisSrid(),
            neighbor_layer.crs().postgisSrid(),
            self.output_geometry_type(input_layer, single), single,
            min_distance, max_distance, neighbor_count, neighbor_id),
            feedback)
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

    def neighbor_id_column(self, parameters: dict, context,
                           layer: QgsVectorLayer) -> str:
        column = self.parameterAsString(
            parameters, self.NEIGHBOR_ID, context)
        if column:
            return column
        keys = layer.primaryKeyAttributes()
        return layer.fields().at(keys[0]).name() if keys else ''

    def generate_nearest_neighbor_query(
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, columns: List[str], neighbor_schema: str,
            neighbor_table: str, neighbor_geom_column: str, srid: int,
            neighbor_srid: int, out_geom_type: str, single: bool,
            min_distance: float, max_distance: float, neighbor_count: int,
            neighbor_id: str) -> str:
        input_geom = f'g1.{quote_identifier(geom_column)}'
        neighbor_geom = f'n.{quote_identifier(neighbor_geom_column)}'
        if neighbor_srid != srid:
            neighbor_geom = f'ST_Transform({neighbor_geom}, {srid})'
        geom_part = f'{input_geom} AS "geom"'
        if single:
            geom_part = f'(ST_Dump({input_geom})).geom::geometry(' \
                        f'{out_geom_type}, {srid}) AS "geom"'
        distance = f'{neighbor_geom} <-> {input_geom}'
        conditions = []
        if min_distance:
            conditions.append(f'{distance} >= {min_distance}')
        if max_distance:
            conditions.append(
                f'ST_DWithin({neighbor_geom}, {input_geom}, {max_distance})')
        where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
        id_source = f'n.{quote_identifier(neighbor_id)} AS neighbor_id, ' \
            if neighbor_id else ''
        id_column = 'g2.neighbor_id AS "neighbor_id", ' if neighbor_id \
            else ''
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('g1', columns)}{id_column}
                    g2.dist AS "distance", {geom_part}
                FROM {source} AS g1
                CROSS JOIN LATERAL (
                    SELECT {id_source}{distance} AS dist
                    FROM {qualified_name(neighbor_schema, neighbor_table)}
                        AS n
                    {where}
                    ORDER BY dist
                    LIMIT {neighbor_count}
                ) AS g2
            );
        '''

    def name(self):
        return 'vector_nearest_neighbor'

    def displayName(self):
        return tr('Nearest Neighbor')

    def shortDescription(self):
        return tr(
            'Finds the nearest points of another layer for every feature.')

    def help_text(self):
        return tr(
            'Finds for every feature of the input layer the given number of '
            'nearest points of the neighbor layer. The feature is written '
            'once for every neighbor found, with the distance in layer units '
            'in the distance column and the neighbor identifier in the '
            'neighbor_id column. The identifier is taken from the chosen '
            'column or, when none is chosen, from the primary key of the '
            'neighbor layer. A maximum distance of 0 means no limit; points '
            'closer than the minimum distance are skipped. Features without '
            'any neighbor in range are left out. The chosen columns are '
            'copied to the result.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorNearestNeighbor()
