# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBand, QgsProcessingParameterBoolean

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxRasterVectorize(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    BAND = 'BAND'
    EXCLUDE_NODATA = 'EXCLUDE_NODATA'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterBand(
            self.BAND, tr('Band number'), 1, self.INPUT))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EXCLUDE_NODATA, tr('Skip nodata pixels'), True))
        self.add_connection_parameter()
        self.add_output_parameters('polygons')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        band = self.parameterAsInt(parameters, self.BAND, context)
        exclude_nodata = self.parameterAsBool(
            parameters, self.EXCLUDE_NODATA, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_vectorize_query(
            out_schema, out_table, schema, table, rast_column, band,
            exclude_nodata, raster_layer.crs().postgisSrid()), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Polygons")} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_vectorize_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, band: int, exclude_nodata: bool,
            srid: int) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT row_number() OVER () AS "id",
                    (dumped).val AS "value",
                    (dumped).geom::geometry(POLYGON, {srid}) AS "geom"
                FROM (
                    SELECT ST_DumpAsPolygons({quote_identifier(rast_column)},
                        {band}, {'TRUE' if exclude_nodata else 'FALSE'})
                        AS dumped
                    FROM {qualified_name(schema, table)}
                ) AS tiles
            );
        '''

    def name(self):
        return 'raster_vectorize'

    def displayName(self):
        return tr('Raster to polygons')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterVectorize()
