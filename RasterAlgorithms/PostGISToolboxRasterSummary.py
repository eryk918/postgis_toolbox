# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBand, QgsProcessingParameterFileDestination, \
    QgsProcessingException, QgsDataSourceUri

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name
from ..utils import tr


class PostGISToolboxRasterSummary(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    BAND = 'BAND'
    SAVE = 'SAVE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterBand(
            self.BAND, tr('Band number'), 1, self.INPUT))
        self.add_connection_parameter()
        self.addParameter(QgsProcessingParameterFileDestination(
            self.SAVE, tr('Output path'), tr('HTML files (*.html)')))

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        band_number = self.parameterAsInt(parameters, self.BAND, context)
        output_path = self.parameterAsFileOutput(
            parameters, self.SAVE, context)

        rows = self.execute_sql(connection, self.generate_statistics_query(
            schema, table, rast_column, band_number), feedback)
        if not rows or rows[0][0] is None:
            raise QgsProcessingException(
                tr('No statistics could be computed for the raster.'))
        if feedback.isCanceled():
            return {}
        count, total, mean, stddev, minimum, maximum = rows[0]
        database = QgsDataSourceUri(connection.uri()).database()
        html = f'''<h3><b>{tr('File analyzed')}</b>: {tr('database')}
            <i>"{database}"</i>, {tr('schema')} <i>"{schema}"</i>,
            {tr('table')} <i>"{table}"</i></h3>
            <p>{tr('Minimum value')}: {minimum},</p>
            <p>{tr('Maximum value')}: {maximum},</p>
            <p>{tr('Range')}: {maximum - minimum},</p>
            <p>{tr('Sum')}: {total},</p>
            <p>{tr('Mean value')}: {mean},</p>
            <p>{tr('Standard deviation')}: {stddev}.</p>'''
        with open(output_path, 'w', encoding='utf-8') as html_file:
            html_file.write(html)
        return {self.SAVE: output_path}

    def generate_statistics_query(self, schema: str, table: str,
                                  rast_column: str, band_number: int) -> str:
        return f'''
            WITH union_raster AS (
                SELECT ST_Union("{rast_column}", {band_number}) AS rast_union
                FROM {qualified_name(schema, table)}
            )
            SELECT (stats).count, (stats).sum, (stats).mean, (stats).stddev,
                (stats).min, (stats).max
            FROM (
                SELECT ST_SummaryStats(rast_union, 1) AS stats
                FROM union_raster
            ) AS summary;
        '''

    def name(self):
        return 'raster_summary'

    def displayName(self):
        return tr('Summary')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterSummary()
