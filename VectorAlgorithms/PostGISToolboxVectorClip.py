# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterBoolean, \
    QgsProcessingParameterEnum

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorClip(PostGISToolboxAlgorithm):
    HELP_PAGE = 'ST_Intersection'
    INPUT = 'INPUT'
    INPUT_CLIP = 'INPUT_CLIP'
    FIELDS = 'FIELDS'
    SINGLE = 'SINGLE'
    RELATION = 'RELATION'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_CLIP, tr('Layer to be clipped')))
        self.addParameter(QgsProcessingParameterEnum(
            self.RELATION, tr('Spatial relation'),
            [tr('Intersects'), tr('Contains or overlaps')], defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))
        self.add_connection_parameter()
        self.add_output_parameters('clip')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        clip_layer = self.get_postgis_layer(
            parameters, self.INPUT_CLIP, context, connection)
        source, geom_column = self.input_source(input_layer)
        clip_schema, clip_table, clip_geom_column = \
            self.layer_table(clip_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        single = self.parameterAsBool(parameters, self.SINGLE, context)
        intersects = self.parameterAsEnum(
            parameters, self.RELATION, context) == 0
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_clip_query(
            out_schema, out_table, source, geom_column, columns,
            clip_schema, clip_table, clip_geom_column,
            input_layer.crs().postgisSrid(),
            clip_layer.crs().postgisSrid(),
            self.output_geometry_type(input_layer, single), single,
            intersects, self.collection_type(input_layer)), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Clipped")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_clip_query(
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, columns: List[str], clip_schema: str,
            clip_table: str, clip_geom_column: str, srid: int,
            clip_srid: int, out_geom_type: str, single: bool,
            intersects: bool, collection_type: int) -> str:
        input_geom = f'g1.{quote_identifier(geom_column)}'
        clip_geom = f'g2.{quote_identifier(clip_geom_column)}'
        if clip_srid != srid:
            clip_geom = f'ST_Transform({clip_geom}, {srid})'
        if intersects:
            condition = f'ST_Intersects({input_geom}, {clip_geom})'
        else:
            condition = f'''ST_Contains({input_geom}, {clip_geom})
                    OR ST_Overlaps({input_geom}, {clip_geom})
                    OR ST_Contains({clip_geom}, {input_geom})'''
        geometry = '(ST_Dump(clipped."geom")).geom' if single \
            else 'ST_Multi(clipped."geom")'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('g1', columns)}
                    ({geometry})::geometry({out_geom_type}, {srid})
                        AS "geom"
                FROM {source} AS g1
                JOIN {qualified_name(clip_schema, clip_table)} AS g2
                    ON {condition}
                CROSS JOIN LATERAL (
                    SELECT ST_CollectionExtract(
                        ST_Intersection({input_geom}, {clip_geom}),
                        {collection_type}) AS "geom"
                ) AS clipped
                WHERE NOT ST_IsEmpty(clipped."geom")
            );
        '''

    def name(self):
        return 'vector_clip'

    def displayName(self):
        return tr('Clip')

    def shortDescription(self):
        return tr('Cuts features to the shape of another layer.')

    def help_text(self):
        return tr(
            'Cuts the features of the input layer to the features of the '
            'second layer with ST_Intersection. One feature is written for '
            'every pair of matching features. With the Intersects relation '
            'every feature sharing any space with the second layer is '
            'clipped, also lines crossing a polygon. Contains or overlaps '
            'takes only pairs where one feature lies inside the other or '
            'both partly overlap, which skips lines crossing a polygon. '
            'Parts of another geometry type, such as a point where two '
            'polygons touch, are left out. If the layers use different '
            'coordinate systems, the second one is transformed to the system '
            'of the input layer. The chosen columns are copied to the '
            'result.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorClip()
