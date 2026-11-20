# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterEnum

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr

CENTROID_FUNCTIONS = ['ST_Centroid', 'ST_PointOnSurface']


class PostGISToolboxVectorCentroids(PostGISToolboxAlgorithm):
    HELP_PAGE = 'ST_Centroid'
    INPUT = 'INPUT'
    FIELDS = 'FIELDS'
    METHOD = 'METHOD'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, tr('Point placement'),
            [tr('Centroid'), tr('Point on surface')], defaultValue=0))
        self.add_connection_parameter()
        self.add_output_parameters('centroids')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        source, geom_column = self.input_source(input_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        method = self.parameterAsEnum(parameters, self.METHOD, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_centroids_query(
            out_schema, out_table, source, geom_column, columns,
            CENTROID_FUNCTIONS[method], input_layer.crs().postgisSrid()),
            feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Centroids")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_centroids_query(
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, columns: List[str], function: str,
            srid: int) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('input_table', columns)}
                    {function}(input_table.{quote_identifier(geom_column)})
                        ::geometry(POINT, {srid}) AS "geom"
                FROM {source} AS input_table
            );
        '''

    def name(self):
        return 'vector_centroids'

    def displayName(self):
        return tr('Centroids')

    def shortDescription(self):
        return tr('Creates one point for every feature.')

    def help_text(self):
        return tr(
            'Creates a point for every feature of the input layer. Centroid '
            'uses ST_Centroid and the point may fall outside the feature; '
            'Point on surface uses ST_PointOnSurface and the point always '
            'lies on the feature. The chosen columns are copied to the '
            'result.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorCentroids()
