# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBoolean

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name
from ..utils import tr


class PostGISToolboxRasterMerge(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    OVERVIEWS = 'OVERVIEWS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERVIEWS, tr('Create raster overviews'), True))
        self.add_connection_parameter()
        self.add_output_parameters('merged_raster', raster=True)

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        overviews = self.parameterAsBool(parameters, self.OVERVIEWS, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table, raster=True)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_raster_merge_query(
            out_schema, out_table, schema, table, rast_column), feedback)
        feedback.setProgress(70)
        self.finish_raster_table(connection, out_schema, out_table, overviews,
                                 feedback, rast_column)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_raster_layer(
            connection, out_schema, out_table,
            f'{tr("Merge tiles")} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_raster_merge_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT 1 AS "rid",
                    ST_Union("{rast_column}") AS "{rast_column}"
                FROM {qualified_name(schema, table)}
            );
        '''

    def name(self):
        return 'raster_merge_tiles'

    def displayName(self):
        return tr('Merge tiles')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterMerge()
