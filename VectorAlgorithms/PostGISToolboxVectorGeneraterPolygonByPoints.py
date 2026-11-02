# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean, \
    QgsProcessing

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorGeneratePolygonFromPoints(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    CONCAVITY_RATIO = 'CONCAVITY_RATIO'
    ALLOW_HOLES = 'ALLOW_HOLES'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input point layer'),
            types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.CONCAVITY_RATIO, tr('Concavity ratio'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0.4,
            minValue=0, maxValue=1))
        self.addParameter(QgsProcessingParameterBoolean(
            self.ALLOW_HOLES, tr('Allow holes?'), True))
        self.add_connection_parameter()
        self.add_output_parameters('polygon_from_points')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        concavity_ratio = self.parameterAsDouble(
            parameters, self.CONCAVITY_RATIO, context)
        allow_holes = self.parameterAsBool(
            parameters, self.ALLOW_HOLES, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_polygon_query(
            out_schema, out_table, schema, table, geom_column,
            concavity_ratio, allow_holes), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Polygon from points")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_polygon_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, concavity_ratio: float,
            allow_holes: bool) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT ST_ConcaveHull(
                    ST_Union({quote_identifier(geom_column)}),
                    {concavity_ratio}, {allow_holes}) AS "geom"
                FROM {qualified_name(schema, table)}
            );
        '''

    def name(self):
        return 'vector_polygon_from_points'

    def displayName(self):
        return tr('Generate polygon from points')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorGeneratePolygonFromPoints()
