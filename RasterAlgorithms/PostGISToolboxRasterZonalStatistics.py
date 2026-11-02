# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBand, QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessing

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr

STATISTICS = ['count', 'sum', 'mean', 'stddev', 'min', 'max']


class PostGISToolboxRasterZonalStatistics(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    BAND = 'BAND'
    ZONES = 'ZONES'
    FIELDS = 'FIELDS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterBand(
            self.BAND, tr('Band number'), 1, self.INPUT))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.ZONES, tr('Zone layer'),
            types=[QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from zone layer'),
            parentLayerParameterName=self.ZONES, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.add_connection_parameter()
        self.add_output_parameters('zonal_statistics')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        zone_layer = self.get_postgis_layer(
            parameters, self.ZONES, context, connection)
        schema, table, rast_column = self.layer_table(raster_layer)
        zone_schema, zone_table, geom_column = self.layer_table(zone_layer)
        band = self.parameterAsInt(parameters, self.BAND, context)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, zone_layer)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_zonal_query(
            out_schema, out_table, schema, table, rast_column, band,
            zone_schema, zone_table, geom_column, columns,
            zone_layer.crs().postgisSrid(),
            raster_layer.crs().postgisSrid()), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Zonal statistics")} {zone_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_zonal_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, band: int, zone_schema: str, zone_table: str,
            geom_column: str, columns: List[str], zone_srid: int,
            raster_srid: int) -> str:
        zone_geometry = 'zones.geom'
        if zone_srid != raster_srid:
            zone_geometry = f'ST_Transform(zones.geom, {raster_srid})'
        statistics = ', '.join(
            f'(stats.summary).{name} AS {quote_identifier(f"_{name}")}'
            for name in STATISTICS)
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                WITH zones AS (
                    SELECT row_number() OVER () AS zone_id,
                        {select_columns('zone_table', columns)}
                        zone_table.{quote_identifier(geom_column)} AS geom
                    FROM {qualified_name(zone_schema, zone_table)}
                        AS zone_table
                ),
                stats AS (
                    SELECT zones.zone_id,
                        ST_SummaryStatsAgg(
                            ST_Clip(tiles.{quote_identifier(rast_column)},
                                {band}, {zone_geometry}, TRUE),
                            1, TRUE) AS summary
                    FROM zones
                    JOIN {qualified_name(schema, table)} AS tiles
                        ON ST_Intersects(tiles.{quote_identifier(rast_column)},
                            {zone_geometry})
                    GROUP BY zones.zone_id
                )
                SELECT {select_columns('zones', columns)}
                    {statistics}, zones.geom AS "geom"
                FROM zones
                LEFT JOIN stats ON stats.zone_id = zones.zone_id
            );
        '''

    def name(self):
        return 'raster_zonal_statistics'

    def displayName(self):
        return tr('Zonal statistics')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterZonalStatistics()
