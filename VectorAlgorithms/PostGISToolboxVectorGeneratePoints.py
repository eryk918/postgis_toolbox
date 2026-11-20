# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterNumber, QgsProcessingParameterBoolean, \
    QgsProcessing, QgsProcessingException, Qgis

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorGeneratePoints(PostGISToolboxAlgorithm):
    HELP_PAGE = 'ST_GeneratePoints'
    INPUT = 'INPUT'
    POINT_COUNT = 'POINT_COUNT'
    SEPARATE = 'SEPARATE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input polygon layer'),
            types=[QgsProcessing.SourceType.TypeVectorPolygon]))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterNumber(
            self.POINT_COUNT, tr('Number of points'),
            type=QgsProcessingParameterNumber.Type.Integer, defaultValue=1,
            minValue=1))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SEPARATE, tr('Save every point as a separate feature'),
            True))
        self.add_connection_parameter()
        self.add_output_parameters('points')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        if input_layer.geometryType() != Qgis.GeometryType.Polygon:
            raise QgsProcessingException(
                tr('Layer "{0}" is not a polygon layer.').format(
                    input_layer.name()))
        source, geom_column = self.input_source(input_layer)
        number_of_points = self.parameterAsInt(
            parameters, self.POINT_COUNT, context)
        separate = self.parameterAsBool(parameters, self.SEPARATE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_points_query(
            out_schema, out_table, source, geom_column,
            number_of_points, separate,
            input_layer.crs().postgisSrid()), feedback)
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
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, number_of_points: int, separate: bool,
            srid: int) -> str:
        points = f'''ST_GeneratePoints(
                    ST_Union({quote_identifier(geom_column)}),
                    {number_of_points})'''
        if not separate:
            return f'''
                CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                    SELECT {points} AS "geom"
                    FROM {source} AS source_table
                );
            '''
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT row_number() OVER () AS "id",
                    dumped.geom::geometry(POINT, {srid}) AS "geom"
                FROM (
                    SELECT (ST_Dump({points})).geom AS geom
                    FROM {source} AS source_table
                ) AS dumped
            );
        '''

    def name(self):
        return 'vector_generate_points'

    def displayName(self):
        return tr('Generate points')

    def shortDescription(self):
        return tr('Creates random points inside polygons.')

    def help_text(self):
        return tr(
            'Creates the given number of random points inside the merged '
            'polygons of the input layer with ST_GeneratePoints. By default '
            'every point is saved as a separate feature with an id column. '
            'With that option disabled all points are saved as one '
            'multipoint feature without attributes.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorGeneratePoints()
