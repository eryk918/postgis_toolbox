# -*- coding: utf-8 -*-
from typing import List, Tuple, Optional

from qgis.core import QgsProcessingAlgorithm, QgsProcessingException, \
    QgsProcessingParameterProviderConnection, \
    QgsProcessingParameterDatabaseSchema, QgsProcessingParameterDatabaseTable, \
    QgsProcessingParameterBoolean, QgsProcessingOutputVectorLayer, \
    QgsProcessingOutputRasterLayer, QgsProcessingContext, \
    QgsProcessingFeedback, QgsProviderConnectionException, \
    QgsAbstractDatabaseProviderConnection, \
    QgsDataSourceUri, QgsVectorLayer, QgsRasterLayer, QgsMapLayer, \
    QgsWkbTypes

from .utils import tr, get_plugin_object, remove_unsupported_chars, \
    PROCESSING_LAYERS_GROUP, quote_identifier, quote_literal, qualified_name, \
    postgres_metadata, connection_uri

OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]


def select_columns(alias: str, columns: List[str]) -> str:
    if not columns:
        return ''
    return ', '.join(
        f'{alias}.{quote_identifier(column)}' for column in columns) + ', '


class PostGISToolboxAlgorithm(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    CONNECTION = 'CONNECTION'
    DEST_SCHEMA = 'DEST_SCHEMA'
    DEST_TABLE = 'DEST_TABLE'
    OVERWRITE = 'OVERWRITE'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'

    def default_connection_name(self) -> Optional[str]:
        plugin = get_plugin_object()
        if not plugin.db or not plugin.connection_name:
            return None
        saved_connection = postgres_metadata().findConnection(
            plugin.connection_name)
        if saved_connection is None:
            return None
        if connection_uri(saved_connection).database() == \
                connection_uri(plugin.db).database():
            return plugin.connection_name
        return None

    def add_connection_parameter(self) -> None:
        self.addParameter(QgsProcessingParameterProviderConnection(
            self.CONNECTION, tr('Database connection'), 'postgres',
            defaultValue=self.default_connection_name()))

    def add_output_parameters(self, default_table: str,
                              raster: bool = False) -> None:
        self.addParameter(QgsProcessingParameterDatabaseSchema(
            self.DEST_SCHEMA, tr('Output schema'),
            connectionParameterName=self.CONNECTION, defaultValue='public'))
        self.addParameter(QgsProcessingParameterDatabaseTable(
            self.DEST_TABLE, tr('Output table name'),
            connectionParameterName=self.CONNECTION,
            schemaParameterName=self.DEST_SCHEMA,
            defaultValue=default_table, allowNewTableNames=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE, tr('Overwrite table if exists'), True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_TO_PROJECT, tr('Add result layer to the project'),
            True))
        if raster:
            self.addOutput(QgsProcessingOutputRasterLayer(
                self.OUTPUT, tr('Output layer')))
        else:
            self.addOutput(QgsProcessingOutputVectorLayer(
                self.OUTPUT, tr('Output layer')))

    def get_connection(
            self, parameters: dict,
            context: QgsProcessingContext) -> QgsAbstractDatabaseProviderConnection:
        connection_name = self.parameterAsConnectionName(
            parameters, self.CONNECTION, context)
        if not connection_name:
            raise QgsProcessingException(
                tr('No database connection selected.'))
        try:
            return postgres_metadata().createConnection(connection_name)
        except QgsProviderConnectionException as error:
            raise QgsProcessingException(str(error))

    def execute_sql(self, connection: QgsAbstractDatabaseProviderConnection,
                    sql: str, feedback: QgsProcessingFeedback) -> list:
        try:
            return connection.executeSql(sql, feedback)
        except QgsProviderConnectionException as error:
            raise QgsProcessingException(f'{error}\n{sql}')

    def get_output_target(self, parameters: dict,
                          context: QgsProcessingContext) -> Tuple[str, str]:
        schema = self.parameterAsSchema(parameters, self.DEST_SCHEMA, context)
        table = remove_unsupported_chars(self.parameterAsDatabaseTableName(
            parameters, self.DEST_TABLE, context))
        if not schema or not table:
            raise QgsProcessingException(tr('Setup correct parameters!'))
        return schema, table

    def prepare_output_table(
            self, connection: QgsAbstractDatabaseProviderConnection,
            parameters: dict, context: QgsProcessingContext,
            feedback: QgsProcessingFeedback, schema: str, table: str,
            raster: bool = False) -> None:
        if self.parameterAsBool(parameters, self.OVERWRITE, context):
            self.drop_table(connection, schema, table, feedback, raster)
        elif connection.tableExists(schema, table):
            raise QgsProcessingException(
                tr('Table "{0}"."{1}" already exists.').format(schema, table))

    def drop_table(self, connection: QgsAbstractDatabaseProviderConnection,
                   schema: str, table: str, feedback: QgsProcessingFeedback,
                   raster: bool = False) -> None:
        if raster:
            overviews = self.execute_sql(connection, f'''
                SELECT o_table_schema, o_table_name
                FROM raster_overviews
                WHERE r_table_schema = {quote_literal(schema)}
                    AND r_table_name = {quote_literal(table)};
            ''', feedback)
            for overview_schema, overview_table in overviews:
                self.execute_sql(connection, f'DROP TABLE IF EXISTS '
                                 f'{qualified_name(overview_schema, overview_table)};',
                                 feedback)
        self.execute_sql(connection, f'DROP TABLE IF EXISTS '
                         f'{qualified_name(schema, table)} CASCADE;',
                         feedback)

    def get_postgis_layer(
            self, parameters: dict, name: str, context: QgsProcessingContext,
            connection: QgsAbstractDatabaseProviderConnection,
            raster: bool = False) -> QgsMapLayer:
        if raster:
            layer = self.parameterAsRasterLayer(parameters, name, context)
        else:
            layer = self.parameterAsVectorLayer(parameters, name, context)
        if layer is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, name))
        self.check_postgis_layer(layer, connection)
        return layer

    def check_postgis_layer(
            self, layer: QgsMapLayer,
            connection: QgsAbstractDatabaseProviderConnection) -> None:
        if layer.providerType() not in ('postgres', 'postgresraster'):
            raise QgsProcessingException(
                tr('Layer "{0}" is not a PostGIS layer.').format(layer.name()))
        layer_uri = QgsDataSourceUri(layer.source())
        conn_uri = connection_uri(connection)
        if layer_uri.database() and conn_uri.database() and (
                layer_uri.database() != conn_uri.database()
                or layer_uri.host() != conn_uri.host()):
            raise QgsProcessingException(
                tr('Layer "{0}" is not stored in the selected database.')
                .format(layer.name()))

    def layer_table(self, layer: QgsMapLayer) -> Tuple[str, str, str]:
        uri = QgsDataSourceUri(layer.source())
        return uri.schema(), uri.table(), uri.geometryColumn() or 'rast'

    def get_input_columns(self, parameters: dict, name: str,
                          context: QgsProcessingContext,
                          layer: QgsVectorLayer) -> List[str]:
        columns = self.parameterAsFields(parameters, name, context)
        return columns or [field.name() for field in layer.fields()]

    def output_geometry_type(self, layer: QgsVectorLayer,
                             single: bool) -> str:
        geometry_type = layer.geometryType()
        if geometry_type == QgsWkbTypes.PointGeometry:
            type_name = 'POINT'
        elif geometry_type == QgsWkbTypes.LineGeometry:
            type_name = 'LINESTRING'
        else:
            type_name = 'POLYGON'
        return type_name if single else f'MULTI{type_name}'

    def create_geometry_index(
            self, connection: QgsAbstractDatabaseProviderConnection,
            schema: str, table: str, feedback: QgsProcessingFeedback,
            column: str = 'geom') -> None:
        self.execute_sql(connection, f'''
            CREATE INDEX {quote_identifier(f'{table}_{column}_idx')}
            ON {qualified_name(schema, table)}
            USING GIST ({quote_identifier(column)});
        ''', feedback)

    def output_wkb_types(
            self, connection: QgsAbstractDatabaseProviderConnection,
            schema: str, table: str,
            feedback: QgsProcessingFeedback) -> List[QgsWkbTypes.Type]:
        rows = self.execute_sql(connection, f'''
            SELECT DISTINCT GeometryType("geom")
            FROM {qualified_name(schema, table)}
            WHERE "geom" IS NOT NULL;
        ''', feedback)
        wkb_types = [QgsWkbTypes.parseType(row[0]) for row in rows if row[0]]
        return [wkb_type for wkb_type in wkb_types
                if wkb_type != QgsWkbTypes.Unknown]

    def create_output_vector_layer(
            self, connection: QgsAbstractDatabaseProviderConnection,
            schema: str, table: str, name: str,
            wkb_type: Optional[QgsWkbTypes.Type] = None) -> QgsVectorLayer:
        uri = QgsDataSourceUri(connection.uri())
        uri.setDataSource(schema, table, 'geom')
        if wkb_type is not None:
            uri.setWkbType(wkb_type)
        layer = QgsVectorLayer(uri.uri(False), name, 'postgres')
        if not layer.isValid():
            raise QgsProcessingException(
                tr('Output layer "{0}" is not valid.').format(name))
        return layer

    def create_output_raster_layer(
            self, connection: QgsAbstractDatabaseProviderConnection,
            schema: str, table: str, name: str) -> QgsRasterLayer:
        uri = QgsDataSourceUri(connection.uri())
        uri.setSchema(schema)
        uri.setTable(table)
        uri.setGeometryColumn('rast')
        layer = QgsRasterLayer(uri.uri(False), name, 'postgresraster')
        if not layer.isValid():
            raise QgsProcessingException(
                tr('Output layer "{0}" is not valid.').format(name))
        return layer

    def register_output_layers(self, layers: List[QgsMapLayer],
                               parameters: dict,
                               context: QgsProcessingContext) -> str:
        load_to_project = self.parameterAsBool(
            parameters, self.LOAD_TO_PROJECT, context)
        for position, layer in enumerate(layers):
            context.temporaryLayerStore().addMapLayer(layer)
            if load_to_project:
                details = QgsProcessingContext.LayerDetails(
                    layer.name(), context.project(),
                    self.OUTPUT if position == 0 else '')
                details.groupName = PROCESSING_LAYERS_GROUP
                context.addLayerToLoadOnCompletion(layer.id(), details)
        return layers[0].id()

    def finish_raster_table(
            self, connection: QgsAbstractDatabaseProviderConnection,
            schema: str, table: str, overviews: bool,
            feedback: QgsProcessingFeedback, column: str = 'rast') -> None:
        self.execute_sql(connection, f'''
            CREATE INDEX {quote_identifier(f'{table}_{column}_gist_idx')}
            ON {qualified_name(schema, table)}
            USING GIST (ST_ConvexHull({quote_identifier(column)}));
        ''', feedback)
        self.execute_sql(connection, f'''
            SELECT AddRasterConstraints(
                {quote_literal(schema)}, {quote_literal(table)},
                {quote_literal(column)},
                TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE, TRUE,
                TRUE, TRUE);
        ''', feedback)
        if not overviews:
            return
        for position, level in enumerate(OVERVIEW_LEVELS):
            if feedback.isCanceled():
                return
            overview_table = f'o_{level}_{table}'
            self.execute_sql(connection, f'DROP TABLE IF EXISTS '
                             f'{qualified_name(schema, overview_table)};',
                             feedback)
            self.execute_sql(connection, f'''
                SELECT ST_CreateOverview(
                    {quote_literal(qualified_name(schema, table))},
                    {quote_literal(column)}, {level}, 'Lanczos');
            ''', feedback)
            self.execute_sql(connection, f'''
                ALTER TABLE {qualified_name(schema, overview_table)}
                ADD COLUMN rid bigserial PRIMARY KEY;
            ''', feedback)
            self.execute_sql(connection, f'''
                CREATE INDEX {quote_identifier(f'{overview_table}_{column}_gist_idx')}
                ON {qualified_name(schema, overview_table)}
                USING GIST (ST_ConvexHull({quote_identifier(column)}));
            ''', feedback)
            feedback.setProgress(
                70 + 30 * (position + 1) / len(OVERVIEW_LEVELS))
