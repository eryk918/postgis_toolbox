# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterNumber, QgsProcessing

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorVoronoi(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    TOLERANCE = 'TOLERANCE'
    BUFFER = 'BUFFER'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer'),
            types=[QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOLERANCE, tr('Snapping tolerance'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0,
            minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER, tr('Extend the diagram beyond the points by'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0,
            minValue=0))
        self.add_connection_parameter()
        self.add_output_parameters('voronoi')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        tolerance = self.parameterAsDouble(
            parameters, self.TOLERANCE, context)
        buffer_size = self.parameterAsDouble(parameters, self.BUFFER, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_voronoi_query(
            out_schema, out_table, schema, table, geom_column, tolerance,
            buffer_size, input_layer.crs().postgisSrid()), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Voronoi")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_voronoi_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, tolerance: float, buffer_size: float,
            srid: int) -> str:
        extent = f'ST_Expand(points.geom, {buffer_size})' \
            if buffer_size > 0 else 'NULL::geometry'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                WITH points AS (
                    SELECT ST_Collect({quote_identifier(geom_column)}) AS geom
                    FROM {qualified_name(schema, table)}
                )
                SELECT row_number() OVER () AS "id",
                    (ST_Dump(ST_VoronoiPolygons(points.geom, {tolerance},
                        {extent}))).geom::geometry(POLYGON, {srid}) AS "geom"
                FROM points
            );
        '''

    def name(self):
        return 'vector_voronoi'

    def displayName(self):
        return tr('Voronoi polygons')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorVoronoi()
