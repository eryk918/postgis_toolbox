# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterNumber

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorGeneratePoints(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    POINT_COUNT = 'POINT_COUNT'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterNumber(
            self.POINT_COUNT, tr('Number of points'),
            type=QgsProcessingParameterNumber.Integer, defaultValue=1,
            minValue=1, maxValue=99999))
        self.add_connection_parameter()
        self.add_output_parameters('points')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        number_of_points = self.parameterAsInt(
            parameters, self.POINT_COUNT, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_points_query(
            out_schema, out_table, schema, table, geom_column,
            number_of_points), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Points")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_points_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, number_of_points: int) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT ST_GeneratePoints(
                    ST_Union({quote_identifier(geom_column)}),
                    {number_of_points}) AS "geom"
                FROM {qualified_name(schema, table)}
            );
        '''

    def name(self):
        return 'vector_generate_points'

    def displayName(self):
        return tr('Generate points')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorGeneratePoints()
