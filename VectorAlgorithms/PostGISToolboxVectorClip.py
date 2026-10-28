# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterBoolean

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorClip(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    INPUT_CLIP = 'INPUT_CLIP'
    FIELDS = 'FIELDS'
    SINGLE = 'SINGLE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_CLIP, tr('Layer to be clipped')))
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
        schema, table, geom_column = self.layer_table(input_layer)
        clip_schema, clip_table, clip_geom_column = \
            self.layer_table(clip_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        single = self.parameterAsBool(parameters, self.SINGLE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_clip_query(
            out_schema, out_table, schema, table, geom_column, columns,
            clip_schema, clip_table, clip_geom_column,
            input_layer.crs().postgisSrid(),
            clip_layer.crs().postgisSrid(),
            self.output_geometry_type(input_layer, single), single),
            feedback)
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
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str], clip_schema: str,
            clip_table: str, clip_geom_column: str, srid: int,
            clip_srid: int, out_geom_type: str, single: bool) -> str:
        input_geom = f'g1.{quote_identifier(geom_column)}'
        clip_geom = f'g2.{quote_identifier(clip_geom_column)}'
        if clip_srid != srid:
            clip_geom = f'ST_Transform({clip_geom}, {srid})'
        intersection = f'ST_Intersection({input_geom}, {clip_geom})'
        if not single:
            intersection = f'ST_Multi({intersection})'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('g1', columns)}
                    ({intersection})::geometry({out_geom_type}, {srid})
                        AS "geom"
                FROM {qualified_name(schema, table)} AS g1,
                    {qualified_name(clip_schema, clip_table)} AS g2
                WHERE ST_Contains({input_geom}, {clip_geom}) IS TRUE
                    OR ST_Overlaps({input_geom}, {clip_geom}) IS TRUE
                    OR ST_Contains({clip_geom}, {input_geom}) IS TRUE
            );
        '''

    def name(self):
        return 'vector_clip'

    def displayName(self):
        return tr('Clip')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorClip()
