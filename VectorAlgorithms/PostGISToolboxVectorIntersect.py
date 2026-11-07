# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorIntersects(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    INPUT_MASK = 'INPUT_MASK'
    FIELDS = 'FIELDS'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT_MASK, tr('Mask layer')))
        self.add_connection_parameter()
        self.add_output_parameters('intersect')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        mask_layer = self.get_postgis_layer(
            parameters, self.INPUT_MASK, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        mask_schema, mask_table, mask_geom_column = \
            self.layer_table(mask_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_intersect_query(
            out_schema, out_table, schema, table, geom_column, columns,
            mask_schema, mask_table, mask_geom_column), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        layer_name = f'{tr("Intersection")} {input_layer.name()}'
        wkb_types = self.output_wkb_types(
            connection, out_schema, out_table, feedback)
        out_layers = [
            self.create_output_vector_layer(
                connection, out_schema, out_table, layer_name, wkb_type)
            for wkb_type in wkb_types
        ] or [self.create_output_vector_layer(
            connection, out_schema, out_table, layer_name)]
        return {
            self.OUTPUT: self.register_output_layers(
                out_layers, parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_intersect_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str], mask_schema: str,
            mask_table: str, mask_geom_column: str) -> str:
        input_geom = f'input_table.{quote_identifier(geom_column)}'
        mask_geom = f'mask_table.{quote_identifier(mask_geom_column)}'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('input_table', columns)}
                    ST_Intersection({input_geom}, {mask_geom}) AS "geom"
                FROM {qualified_name(schema, table)} AS input_table
                JOIN {qualified_name(mask_schema, mask_table)} AS mask_table
                ON ST_Intersects({input_geom}, {mask_geom})
            );
        '''

    def name(self):
        return 'vector_intersect'

    def displayName(self):
        return tr('Intersection')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorIntersects()
