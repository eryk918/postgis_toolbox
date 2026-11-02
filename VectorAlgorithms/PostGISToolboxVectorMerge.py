# -*- coding: utf-8 -*-
from typing import List

from qgis.core import QgsProcessingParameterMultipleLayers, \
    QgsProcessingParameterBoolean, QgsProcessingException, QgsProcessing, \
    QgsVectorLayer

from ..postgis_toolbox_algorithm import PostGISToolboxAlgorithm, \
    qualified_name, quote_identifier, select_columns
from ..utils import tr


class PostGISToolboxVectorMerge(PostGISToolboxAlgorithm):
    INPUT = 'INPUT'
    SINGLE = 'SINGLE'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT, tr('Input layers'), QgsProcessing.TypeVector))
        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))
        self.add_connection_parameter()
        self.add_output_parameters('merge')

    def processAlgorithm(self, parameters, context, feedback):
        connection = self.get_connection(parameters, context)
        layers = self.parameterAsLayerList(parameters, self.INPUT, context)
        if not layers:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT))
        for layer in layers:
            self.check_postgis_layer(layer, connection)
        if len({layer.geometryType() for layer in layers}) > 1:
            raise QgsProcessingException(
                tr('Input layers must have the same geometry type.'))
        single = self.parameterAsBool(parameters, self.SINGLE, context)
        out_schema, out_table = self.get_output_target(parameters, context)

        self.prepare_output_table(connection, parameters, context, feedback,
                                  out_schema, out_table)
        if feedback.isCanceled():
            return {}
        self.execute_sql(connection, self.generate_merge_query(
            out_schema, out_table, layers, layers[0].crs().postgisSrid(),
            self.output_geometry_type(layers[0], single), single), feedback)
        feedback.setProgress(80)
        self.create_geometry_index(connection, out_schema, out_table, feedback)
        if feedback.isCanceled():
            return {}

        out_layer = self.create_output_vector_layer(
            connection, out_schema, out_table,
            f'{tr("Merged")} {layers[0].name()}')
        return {
            self.OUTPUT: self.register_output_layers(
                [out_layer], parameters, context),
            self.DEST_SCHEMA: out_schema,
            self.DEST_TABLE: out_table
        }

    def generate_merge_query(
            self, out_schema: str, out_table: str,
            layers: List[QgsVectorLayer], base_srid: int,
            out_geom_type: str, single: bool) -> str:
        selects = []
        for position, layer in enumerate(layers, start=1):
            schema, table, geom_column = self.layer_table(layer)
            alias = f'g{position}'
            columns = [field.name() for field in layer.fields()]
            geom_part = f'{alias}.{quote_identifier(geom_column)}'
            if layer.crs().postgisSrid() != base_srid:
                geom_part = f'ST_Transform({geom_part}, {base_srid})'
            if single:
                geom_part = f'(ST_Dump({geom_part})).geom::geometry(' \
                            f'{out_geom_type}, {base_srid})'
            selects.append(f'''
                SELECT {select_columns(alias, columns)}{geom_part} AS "geom"
                FROM {qualified_name(schema, table)} AS {alias}
            ''')
        return f'''
            CREATE TABLE {qualified_name(out_schema, out_table)} AS (
                {' UNION '.join(selects)}
            );
        '''

    def name(self):
        return 'vector_merge'

    def displayName(self):
        return tr('Merge')

    def group(self):
        return tr('Vector')

    def groupId(self):
        return 'vector'

    def createInstance(self):
        return PostGISToolboxVectorMerge()
