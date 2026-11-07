# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterNumber, \
    QgsProcessingParameterBoolean

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorSimplify(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    FIELDS = 'FIELDS'
    TOLERANCE = 'TOLERANCE'
    PRESERVE_TOPOLOGY = 'PRESERVE_TOPOLOGY'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOLERANCE, tr('Tolerance'),
            type=QgsProcessingParameterNumber.Double, defaultValue=10,
            minValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.PRESERVE_TOPOLOGY, tr('Preserve topology'), True))
        self.add_connection_parameter()
        self.add_output_parameters('simplified')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        tolerance = self.parameterAsDouble(
            parameters, self.TOLERANCE, context)
        preserve = self.parameterAsBool(
            parameters, self.PRESERVE_TOPOLOGY, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_simplify_query(
            out_schema, out_table, schema, table, geom_column, columns,
            tolerance, preserve), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Simplified")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_simplify_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, columns: List[str], tolerance: float,
            preserve: bool) -> str:
        function = 'ST_SimplifyPreserveTopology' if preserve \
            else 'ST_Simplify'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('input_table', columns)}
                    {function}(input_table.{quote_identifier(geom_column)},
                        {tolerance}) AS "geom"
                FROM {qualified_name(schema, table)} AS input_table
            );
        '''

    def name(self):
        return 'vector_simplify'

    def displayName(self):
        return tr('Simplify')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorSimplify()
