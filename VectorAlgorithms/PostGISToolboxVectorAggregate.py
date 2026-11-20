# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorAggregate(PostGISToolboxAlgorithm):
    HELP_PAGE = 'ST_Union'
    INPUT = 'INPUT'
    GROUP_FIELD = 'GROUP_FIELD'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.add_selected_parameter()
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_FIELD, tr('Group by column'),
            parentLayerParameterName=self.INPUT))
        self.add_connection_parameter()
        self.add_output_parameters('aggregate')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        source, geom_column = self.input_source(input_layer)
        group_column = self.parameterAsString(
            parameters, self.GROUP_FIELD, context)
        columns = [field.name() for field in input_layer.fields()
                   if field.name() != group_column]
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_aggregate_query(
            out_schema, out_table, source, geom_column, columns,
            group_column), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Aggregate")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_aggregate_query(
            self, out_schema: str, out_table: str, source: str,
            geom_column: str, columns: List[str], group_column: str) -> str:
        aggregated_columns = ''.join(
            f"STRING_AGG(DISTINCT {quote_identifier(column)}::TEXT, ', ') "
            f'AS {quote_identifier(column)}, '
            for column in columns
        )
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT {aggregated_columns}{quote_identifier(group_column)},
                    ST_Union({quote_identifier(geom_column)}) AS "geom"
                FROM {source} AS source_table
                GROUP BY {quote_identifier(group_column)}
            );
        '''

    def name(self):
        return 'vector_aggregate'

    def displayName(self):
        return tr('Aggregate')

    def shortDescription(self):
        return tr(
            'Merges features sharing a value in the chosen column into one '
            'feature.')

    def help_text(self):
        return tr(
            'Groups features by the values of the chosen column and merges '
            'the geometries of each group with ST_Union. The remaining '
            'columns are kept as text with the distinct values of the group '
            'separated by commas.')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorAggregate()
