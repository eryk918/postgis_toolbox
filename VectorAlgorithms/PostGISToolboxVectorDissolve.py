# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingParameterVectorLayer, \
    QgsProcessingParameterField

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier
from ..utils import tr


class PostGISToolboxVectorDissolve(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    GROUP_FIELD = 'GROUP_FIELD'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, tr('Input layer')))
        self.addParameter(QgsProcessingParameterField(
            self.GROUP_FIELD, tr('Dissolve by column'),
            parentLayerParameterName=self.INPUT, optional=True))
        self.add_connection_parameter()
        self.add_output_parameters('dissolved')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        input_layer = self.get_postgis_layer(
            parameters, self.INPUT, context, connection)
        schema, table, geom_column = self.layer_table(input_layer)
        group_column = self.parameterAsString(
            parameters, self.GROUP_FIELD, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_dissolve_query(
            out_schema, out_table, schema, table, geom_column, group_column,
            self.output_geometry_type(input_layer, False),
            input_layer.crs().postgisSrid()), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Dissolved")} {input_layer.name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_dissolve_query(
            self, out_schema: str, out_table: str, schema: str, table: str,
            geom_column: str, group_column: str, out_geom_type: str,
            srid: int) -> str:
        geometry = f'''
            ST_Multi(ST_Union({quote_identifier(geom_column)}))
                ::geometry({out_geom_type}, {srid}) AS "geom"
        '''
        if group_column:
            group = quote_identifier(group_column)
            return f'''
                CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                    SELECT {group}, {geometry}
                    FROM {qualified_name(schema, table)}
                    GROUP BY {group}
                );
            '''
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                SELECT 1 AS "id", {geometry}
                FROM {qualified_name(schema, table)}
            );
        '''

    def name(self):
        return 'vector_dissolve'

    def displayName(self):
        return tr('Dissolve')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorDissolve()
