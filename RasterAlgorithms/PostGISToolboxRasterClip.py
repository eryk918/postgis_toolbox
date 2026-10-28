# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterMapLayer, QgsProcessingParameterBoolean, \
    QgsProcessingException, QgsVectorLayer, QgsFeatureRequest, \
    QgsGeometry, QgsCoordinateTransform, QgsMapLayer, QgsRasterLayer

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_literal
from ..utils import tr


class PostGISToolboxRasterClip(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    INPUT_CLIP = 'INPUT_CLIP'
    CREATE_OVERVIEWS = 'CREATE_OVERVIEWS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, tr('Input raster layer')))
        self.addParameter(QgsProcessingParameterMapLayer(
            self.INPUT_CLIP, tr('Mask layer')))
        self.addParameter(QgsProcessingParameterBoolean(
            self.CREATE_OVERVIEWS, tr('Create raster overviews'), True))
        self.add_connection_parameter()
        self.add_output_parameters('clip', raster=True)

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        raster_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection, raster=True)
        mask_layer = self.parameterAsLayer(
            parameters, self.INPUT_CLIP, context)
        if mask_layer is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT_CLIP))
        schema, table, rast_column = self.layer_table(raster_layer)
        mask_geometry = self.mask_geometry(mask_layer, raster_layer, context)
        overviews = self.parameterAsBool(
            parameters, self.CREATE_OVERVIEWS, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table, raster=True)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_raster_clip_query(
            out_schema, out_table, schema, table, rast_column,
            mask_geometry.asWkt(), raster_layer.crs().postgisSrid()),
            feedback)
        feedback.setProgress(70)
        self.finish_raster_table(connection, out_schema, out_table, overviews,
                                 feedback, rast_column)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_raster_layer(
            connection, out_schema, out_table,
            f'{tr("Clip")} {raster_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def mask_geometry(self, mask_layer: QgsMapLayer,
                      raster_layer: QgsRasterLayer, context) -> QgsGeometry:
        if isinstance(mask_layer, QgsVectorLayer):
            request = QgsFeatureRequest().setDestinationCrs(
                raster_layer.crs(), context.transformContext())
            geometry = QgsGeometry()
            for feature in mask_layer.getFeatures(request):
                geometry = feature.geometry() if geometry.isNull() \
                    else geometry.combine(feature.geometry())
        else:
            geometry = QgsGeometry.fromRect(mask_layer.extent())
            geometry.transform(QgsCoordinateTransform(
                mask_layer.crs(), raster_layer.crs(),
                context.transformContext()))
        if geometry.isNull() or geometry.isEmpty():
            raise QgsProcessingException(
                tr('Mask layer "{0}" has no geometry.').format(
                    mask_layer.name()))
        return geometry

    def generate_raster_clip_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            rast_column: str, mask_wkt: str, srid: int) -> str:
        mask_geom = f'ST_GeomFromText({quote_literal(mask_wkt)}, {srid})'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT "rid",
                    ST_Clip("{rast_column}", {mask_geom}) AS "{rast_column}"
                FROM {qualified_name(schema, table)}
                WHERE ST_Intersects("{rast_column}", {mask_geom})
            );
        '''

    def name(self):
        return 'raster_clip'

    def displayName(self):
        return tr('Clip')

    def group(self):
        return tr('Raster')

    def groupId(self):
        return 'raster'

    def createInstance(self):
        return PostGISToolboxRasterClip()
