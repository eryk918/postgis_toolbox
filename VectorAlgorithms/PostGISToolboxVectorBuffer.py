# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterNumber

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorBuffer(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    FIELDS = 'FIELDS'
    BUFFER_SIZE = 'BUFFER_SIZE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER_SIZE, tr('Buffer size'),
            type=QgsProcessingParameterNumber.Double, defaultValue=10,
            minValue=0, maxValue=99999))
        self.add_connection_parameter()
        self.add_output_parameters('buffer')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        buffer_size = self.parameterAsDouble(
            parameters, self.BUFFER_SIZE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_buffer_query(
            out_schema, out_table, schema, table, geom_column, columns,
            buffer_size), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Buffer")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_buffer_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str],
            buffer_size: float) -> str:
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('input_table', columns)}
                    ST_Buffer(input_table.{quote_identifier(geom_column)},
                        {buffer_size}) AS "geom"
                FROM {qualified_name(schema, table)} AS input_table
            );
        '''

    def name(self):
        return 'vector_buffer'

    def displayName(self):
        return tr('Buffer')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorBuffer()
