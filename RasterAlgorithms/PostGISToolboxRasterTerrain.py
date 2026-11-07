# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBoolean, QgsProcessingParameterBand, \
    QgsProcessingParameterEnum, QgsProcessingParameterNumber

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr

SLOPE_UNITS = ['DEGREES', 'RADIANS', 'PERCENT']


class PostGISToolboxRasterTerrain(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    BAND = 'BAND'
    METHOD = 'METHOD'
    UNITS = 'UNITS'
    AZIMUTH = 'AZIMUTH'
    ALTITUDE = 'ALTITUDE'
    CREATE_OVERVIEWS = 'CREATE_OVERVIEWS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterBand(
            self.BAND, tr('Band number'), 1, self.INPUT))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, tr('Analysis'),
            [tr('Slope'), tr('Aspect'), tr('Hillshade')], defaultValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            self.UNITS, tr('Slope units'),
            [tr('Degrees'), tr('Radians'), tr('Percent')], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.AZIMUTH, tr('Hillshade azimuth'),
            type=QgsProcessingParameterNumber.Double, defaultValue=315,
            minValue=0, maxValue=360))
        self.addParameter(QgsProcessingParameterNumber(
            self.ALTITUDE, tr('Hillshade sun altitude'),
            type=QgsProcessingParameterNumber.Double, defaultValue=45,
            minValue=0, maxValue=90))
        self.addParameter(QgsProcessingParameterBoolean(
            self.CREATE_OVERVIEWS, tr('Create raster overviews'), True))
        self.add_connection_parameter()
        self.add_output_parameters('terrain', raster=True)

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        band = self.parameterAsInt(parameters, self.BAND, context)
        method = self.parameterAsEnum(parameters, self.METHOD, context)
        units = SLOPE_UNITS[self.parameterAsEnum(
            parameters, self.UNITS, context)]
        azimuth = self.parameterAsDouble(parameters, self.AZIMUTH, context)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)
        overviews = self.parameterAsBool(
            parameters, self.CREATE_OVERVIEWS, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table, raster=True)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_terrain_query(
            out_schema, out_table, schema, table, rast_column, band, method,
            units, azimuth, altitude), feedback)
        feedback.setProgress(70)
        self.finish_raster_table(connection, out_schema, out_table, overviews,
                                 feedback)
        if feedback.isCanceled():
            return {}

        labels = [tr('Slope'), tr('Aspect'), tr('Hillshade')]
        out_layer = self.create_output_raster_layer(
            connection, out_schema, out_table,
            f'{labels[method]} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_terrain_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, band: int, method: int, units: str,
            azimuth: float, altitude: float) -> str:
        if method == 0:
            function = f"ST_Slope(neighbors.rast, 1, tiles.rast, '32BF', " \
                       f"'{units}', 1.0, FALSE)"
        elif method == 1:
            function = "ST_Aspect(neighbors.rast, 1, tiles.rast, '32BF', " \
                       "'DEGREES', FALSE)"
        else:
            function = f"ST_HillShade(neighbors.rast, 1, tiles.rast, " \
                       f"'32BF', {azimuth}, {altitude}, 255.0, 1.0, FALSE)"
        source = quote_identifier(rast_column)
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                WITH tiles AS (
                    SELECT row_number() OVER () AS rid, {source} AS rast
                    FROM {qualified_name(schema, table)}
                    WHERE {source} IS NOT NULL
                )
                SELECT tiles.rid AS "rid", {function} AS "rast"
                FROM tiles
                CROSS JOIN LATERAL (
                    SELECT ST_Union(other.rast, {band}) AS rast
                    FROM tiles AS other
                    WHERE ST_Intersects(tiles.rast, other.rast)
                ) AS neighbors
            );
        '''

    def name(self):
        return 'raster_terrain'

    def displayName(self):
        return tr('Terrain analysis')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterTerrain()
