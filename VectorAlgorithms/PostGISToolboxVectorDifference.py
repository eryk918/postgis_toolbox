# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterBoolean

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorDifference(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    INPUT_DIFF = 'INPUT_DIFF'
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
            self.INPUT_DIFF, tr('Layer to be subtracted')))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))
        self.add_connection_parameter()
        self.add_output_parameters('difference')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        diff_layer = self.get_postgis_layer(
            parameters, self.INPUT_DIFF, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        diff_schema, diff_table, diff_geom_column = \
            self.layer_table(diff_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        single = self.parameterAsBool(parameters, self.SINGLE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_difference_query(
            out_schema, out_table, schema, table, geom_column, columns,
            diff_schema, diff_table, diff_geom_column,
            input_layer.crs().postgisSrid(),
            diff_layer.crs().postgisSrid(),
            self.output_geometry_type(input_layer, single), single),
            feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Subtracted")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_difference_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str], diff_schema: str,
            diff_table: str, diff_geom_column: str, srid: int,
            diff_srid: int, out_geom_type: str, single: bool) -> str:
        input_geom = f'g1.{quote_identifier(geom_column)}'
        diff_geom = 'g2."geom"'
        if diff_srid != srid:
            diff_geom = f'ST_Transform({diff_geom}, {srid})'
        difference = f'ST_Difference({input_geom}, {diff_geom})'
        if not single:
            difference = f'ST_Multi({difference})'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                WITH union_geom AS (
                    SELECT ST_Union({quote_identifier(diff_geom_column)})
                        AS "geom"
                    FROM {qualified_name(diff_schema, diff_table)}
                )
                SELECT {select_columns('g1', columns)}
                    ({difference})::geometry({out_geom_type}, {srid})
                        AS "geom"
                FROM {qualified_name(schema, table)} AS g1, union_geom AS g2
            );
        '''

    def name(self):
        return 'vector_difference'

    def displayName(self):
        return tr('Difference')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorDifference()
