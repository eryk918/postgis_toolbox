# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterBoolean, QgsProcessingParameterNumber, \
    QgsProcessingParameterEnum

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name
from ..utils import tr

RESAMPLING_ALGORITHMS = ['NearestNeighbor', 'Bilinear', 'Cubic',
                         'CubicSpline', 'Lanczos']


class PostGISToolboxRasterResample(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    SCALE_VALUE = 'SCALE_VALUE'
    ALG_NAME = 'ALG_NAME'
    MAX_ERR = 'MAX_ERR'
    OVERVIEWS = 'OVERVIEWS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterNumber(
            self.SCALE_VALUE, tr('Spatial resolution'),
            type=QgsProcessingParameterNumber.Double, defaultValue=100,
            minValue=0.0000001, maxValue=99999999))
        self.addParameter(QgsProcessingParameterEnum(
            self.ALG_NAME, tr('Resampling algorithm'),
            options=RESAMPLING_ALGORITHMS, allowMultiple=False,
            defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_ERR, tr('Maximum percentage error'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0.125,
            minValue=0, maxValue=100))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERVIEWS, tr('Create raster overviews'), True))
        self.add_connection_parameter()
        self.add_output_parameters('resampled_raster', raster=True)

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        schema, table, rast_column = self.layer_table(raster_layer)
        scale_value = self.parameterAsDouble(
            parameters, self.SCALE_VALUE, context)
        resampling_algorithm = RESAMPLING_ALGORITHMS[
            self.parameterAsEnum(parameters, self.ALG_NAME, context)]
        max_error = self.parameterAsDouble(parameters, self.MAX_ERR, context)
        overviews = self.parameterAsBool(parameters, self.OVERVIEWS, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table, raster=True)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_raster_resample_query(
            out_schema, out_table, schema, table, rast_column, scale_value,
            resampling_algorithm, max_error), feedback)
        feedback.setProgress(70)
        self.finish_raster_table(connection, out_schema, out_table, overviews,
                                 feedback, rast_column)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_raster_layer(
            connection, out_schema, out_table,
            f'{tr("Resample")} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_raster_resample_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, scale_value: float,
            resampling_algorithm: str, max_error: float) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT "rid",
                    ST_Rescale("{rast_column}", {scale_value},
                        '{resampling_algorithm}', {max_error})
                        AS "{rast_column}"
                FROM {qualified_name(schema, table)}
            );
        '''

    def name(self):
        return 'raster_resample'

    def displayName(self):
        return tr('Resample')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterResample()
