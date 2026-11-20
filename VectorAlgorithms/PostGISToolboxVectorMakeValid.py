# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField, QgsProcessingParameterEnum

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr

REPAIR_METHODS = ['ST_Buffer', 'ST_MakeValid']


class PostGISToolboxVectorMakeValid(PostGISToolboxAlgorithm):
    HELP_PAGE = 'ST_MakeValid'
    INPUT = 'INPUT'
    FIELDS = 'FIELDS'
    METHOD = 'METHOD'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, tr('Choose columns from input layer'),
            parentLayerParameterName=self.INPUT, allowMultiple=True,
            optional=True, defaultToAllFields=True))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, tr('Repair method'), options=REPAIR_METHODS,
            allowMultiple=False, defaultValue=0))
        self.add_connection_parameter()
        self.add_output_parameters('repaired_vectors')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        source, geom_column = self.input_source(input_layer)
        columns = self.get_input_columns(
            parameters, self.FIELDS, context, input_layer)
        repair_method = REPAIR_METHODS[
            self.parameterAsEnum(parameters, self.METHOD, context)]
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_repair_query(
            out_schema, out_table, source, geom_column, columns,
            repair_method), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Repaired")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_repair_query(
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, columns: List[str],
            repair_method: str) -> str:
        input_geom = f'input_table.{quote_identifier(geom_column)}'
        if repair_method == 'ST_Buffer':
            geom_query = f'ST_Buffer(ST_Buffer({input_geom}, 0.001), -0.001)'
        else:
            geom_query = f'ST_MakeValid({input_geom})'
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {select_columns('input_table', columns)}
                    {geom_query} AS "geom"
                FROM {source} AS input_table
            );
        '''

    def name(self):
        return 'repair_geometry'

    def displayName(self):
        return tr('Repair geometry')

    def shortDescription(self):
        return tr('Repairs invalid geometries.')

    def help_text(self):
        return tr(
            'Repairs the geometries of the input layer. ST_MakeValid fixes '
            'them without losing vertices; ST_Buffer applies a buffer of '
            '0.001 layer units outwards and back inwards, which is meant for '
            'polygons. The chosen columns are copied to the result.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorMakeValid()
