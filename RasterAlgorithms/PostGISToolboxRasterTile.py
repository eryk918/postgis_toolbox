# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBoolean, QgsProcessingParameterNumber

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name
from ..utils import tr


class PostGISToolboxRasterTile(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    SIZE_X = 'SIZE_X'
    SIZE_Y = 'SIZE_Y'
    OVERVIEWS = 'OVERVIEWS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterNumber(
            self.SIZE_X, tr('Tile size X'), minValue=1, defaultValue=100))
        self.addParameter(QgsProcessingParameterNumber(
            self.SIZE_Y, tr('Tile size Y'), minValue=1, defaultValue=100))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERVIEWS, tr('Create raster overviews'), True))
        self.add_connection_parameter()
        self.add_output_parameters('tiled_raster', raster=True)

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        size_x = self.parameterAsInt(parameters, self.SIZE_X, context)
        size_y = self.parameterAsInt(parameters, self.SIZE_Y, context)
        overviews = self.parameterAsBool(parameters, self.OVERVIEWS, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table, raster=True)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_raster_tiles_query(
            out_schema, out_table, schema, table, rast_column, size_x,
            size_y), feedback)
        feedback.setProgress(70)
        self.finish_raster_table(connection, out_schema, out_table, overviews,
                                 feedback, rast_column)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_raster_layer(
            connection, out_schema, out_table,
            f'{tr("Tiles")} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_raster_tiles_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, size_x: int, size_y: int) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                WITH merged_raster AS (
                    SELECT ST_Union("{rast_column}") AS merged
                    FROM {qualified_name(schema, table)}
                )
                SELECT row_number() OVER () AS "rid",
                    ST_Tile(merged, {size_x}, {size_y}) AS "{rast_column}"
                FROM merged_raster
            );
        '''

    def name(self):
        return 'raster_tiles'

    def displayName(self):
        return tr('Tiles')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterTile()
