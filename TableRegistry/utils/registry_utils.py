# -*- coding: utf-8 -*-
from typing import Dict, List, Optional, Tuple

from qgis.core import QgsAbstractDatabaseProviderConnection

from ...utils import make_query, quote_literal, quote_identifier, \
    qualified_name

RELKIND_KEYWORDS = {
    'r': 'TABLE',
    'p': 'TABLE',
    'v': 'VIEW',
    'm': 'MATERIALIZED VIEW',
    'f': 'FOREIGN TABLE',
}

EXCLUDED_SCHEMAS = ('pg_catalog', 'information_schema', 'pg_toast',
                    'topology', 'tiger', 'tiger_data')

POSTGIS_RELATIONS = ('spatial_ref_sys', 'geometry_columns',
                     'geography_columns', 'raster_columns',
                     'raster_overviews')


class TableInfo:
    def __init__(self, schema: str, name: str, relkind: str,
                 estimated_rows: int) -> None:
        self.schema = schema
        self.name = name
        self.relkind = relkind
        self.estimated_rows = estimated_rows
        self.geometry_columns = []
        self.raster_column = None
        self.raster_srid = None
        self.num_bands = None
        self.pixel_types = None
        self.scale = None
        self.block_size = None
        self.overviews = []
        self.is_overview = False

    def qualified_name(self) -> str:
        return qualified_name(self.schema, self.name)

    def is_vector(self) -> bool:
        return bool(self.geometry_columns)

    def is_raster(self) -> bool:
        return self.raster_column is not None

    def keyword(self) -> str:
        return RELKIND_KEYWORDS.get(self.relkind, 'TABLE')


def relations_query() -> str:
    excluded = ', '.join(quote_literal(name) for name in EXCLUDED_SCHEMAS)
    postgis = ', '.join(quote_literal(name) for name in POSTGIS_RELATIONS)
    return f'''
        SELECT n.nspname, c.relname, c.relkind, c.reltuples::bigint
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'v', 'm', 'p', 'f')
            AND n.nspname NOT IN ({excluded})
            AND n.nspname NOT LIKE 'pg\\_temp\\_%'
            AND n.nspname NOT LIKE 'pg\\_toast\\_temp\\_%'
            AND position('_ogr_' IN c.relname) <> 1
            AND NOT (n.nspname = 'public' AND c.relname IN ({postgis}))
        ORDER BY n.nspname, c.relname;
    '''


geometry_columns_query = '''
    SELECT f_table_schema, f_table_name, f_geometry_column, type, srid,
           coord_dimension
    FROM geometry_columns
    ORDER BY f_table_schema, f_table_name, f_geometry_column;
'''

raster_columns_query = '''
    SELECT r_table_schema, r_table_name, r_raster_column, srid, num_bands,
           pixel_types, scale_x, scale_y, blocksize_x, blocksize_y
    FROM raster_columns;
'''

raster_overviews_query = '''
    SELECT r_table_schema, r_table_name, o_table_schema, o_table_name,
           overview_factor
    FROM raster_overviews
    ORDER BY overview_factor;
'''


def load_tables(
        connection: QgsAbstractDatabaseProviderConnection) -> List[TableInfo]:
    rows = make_query(connection, relations_query())
    if rows is None:
        return []
    tables = {}
    for schema, name, relkind, estimated_rows in rows:
        tables[(schema, name)] = TableInfo(
            schema, name, relkind, estimated_rows)
    for row in make_query(connection, geometry_columns_query) or []:
        info = tables.get((row[0], row[1]))
        if info is not None:
            info.geometry_columns.append((row[2], row[3], row[4], row[5]))
    for row in make_query(connection, raster_columns_query) or []:
        info = tables.get((row[0], row[1]))
        if info is None:
            continue
        info.raster_column = row[2]
        info.raster_srid = row[3]
        info.num_bands = row[4]
        info.pixel_types = row[5]
        info.scale = (row[6], row[7])
        info.block_size = (row[8], row[9])
    for row in make_query(connection, raster_overviews_query) or []:
        info = tables.get((row[0], row[1]))
        overview = tables.get((row[2], row[3]))
        if overview is not None:
            overview.is_overview = True
        if info is not None:
            info.overviews.append((row[2], row[3], row[4]))
    return [info for info in tables.values() if not info.is_overview]


def table_columns(connection: QgsAbstractDatabaseProviderConnection,
                  info: TableInfo) -> List[Tuple[str, str]]:
    rows = make_query(connection, f'''
        SELECT a.attname, format_type(a.atttypid, a.atttypmod),
               col_description(a.attrelid, a.attnum)
        FROM pg_attribute a
        WHERE a.attrelid = {quote_literal(info.qualified_name())}::regclass
            AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum;
    ''')
    return [(row[0], f'{row[1]} - {row[2]}' if row[2] else row[1])
            for row in rows or []]


def table_comment(connection: QgsAbstractDatabaseProviderConnection,
                  info: TableInfo) -> str:
    rows = make_query(connection, f'''
        SELECT obj_description(
            {quote_literal(info.qualified_name())}::regclass, 'pg_class');
    ''')
    return (rows[0][0] if rows else None) or ''


def primary_key(connection: QgsAbstractDatabaseProviderConnection,
                info: TableInfo) -> Optional[str]:
    rows = make_query(connection, f'''
        SELECT string_agg(a.attname, ', ' ORDER BY a.attnum)
        FROM pg_index i
        JOIN pg_attribute a
            ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = {quote_literal(info.qualified_name())}::regclass
            AND i.indisprimary;
    ''')
    if not rows or not rows[0][0]:
        return None
    return rows[0][0]


def table_indexes(connection: QgsAbstractDatabaseProviderConnection,
                  info: TableInfo) -> List[Tuple[str, str]]:
    rows = make_query(connection, f'''
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = {quote_literal(info.schema)}
            AND tablename = {quote_literal(info.name)}
        ORDER BY indexname;
    ''')
    return [(row[0], row[1]) for row in rows or []]


def rename_sql(info: TableInfo, new_name: str) -> str:
    statements = [
        f'ALTER {info.keyword()} {info.qualified_name()} '
        f'RENAME TO {quote_identifier(new_name)};'
    ]
    for schema, table, factor in info.overviews:
        new_overview = f'o_{factor}_{new_name}'
        statements.append(f'''
            SELECT DropOverviewConstraints(
                {quote_literal(schema)}, {quote_literal(table)},
                {quote_literal(info.raster_column)});
            ALTER TABLE {qualified_name(schema, table)}
            RENAME TO {quote_identifier(new_overview)};
            SELECT AddOverviewConstraints(
                {quote_literal(schema)}, {quote_literal(new_overview)},
                {quote_literal(info.raster_column)},
                {quote_literal(info.schema)}, {quote_literal(new_name)},
                {quote_literal(info.raster_column)}, {factor});
        ''')
    return '\n'.join(statements)


def drop_sql(info: TableInfo) -> str:
    statements = [
        f'DROP TABLE {qualified_name(schema, table)};'
        for schema, table, factor in info.overviews
    ]
    statements.append(f'DROP {info.keyword()} {info.qualified_name()};')
    return '\n'.join(statements)


def rename_table(connection: QgsAbstractDatabaseProviderConnection,
                 info: TableInfo, new_name: str) -> bool:
    return make_query(connection, rename_sql(info, new_name)) is not None


def drop_table(connection: QgsAbstractDatabaseProviderConnection,
               info: TableInfo) -> bool:
    return make_query(connection, drop_sql(info)) is not None


def table_names_in_schema(tables: List[TableInfo],
                          schema: str) -> List[str]:
    names = [info.name for info in tables if info.schema == schema]
    for info in tables:
        if info.schema == schema:
            names.extend(table for _, table, _ in info.overviews)
    return names


def kind_key(info: TableInfo) -> str:
    if info.is_raster():
        return 'raster'
    if info.is_vector():
        return 'vector'
    return info.relkind


def pixel_types_label(info: TableInfo) -> str:
    if isinstance(info.pixel_types, (list, tuple)):
        return ', '.join(str(value) for value in info.pixel_types)
    return str(info.pixel_types or '')


def srid_unit(connection: QgsAbstractDatabaseProviderConnection,
              srid: Optional[int]) -> str:
    if not srid:
        return ''
    rows = make_query(connection, f'''
        SELECT proj4text FROM spatial_ref_sys WHERE srid = {int(srid)};
    ''')
    proj4 = (rows[0][0] if rows else None) or ''
    if '+proj=longlat' in proj4:
        return '°'
    for token in proj4.split():
        if token.startswith('+units='):
            return token[len('+units='):]
    return ''


def format_size(value: float) -> str:
    return f'{abs(value):.6f}'.rstrip('0').rstrip('.')


def raster_resolution(connection: QgsAbstractDatabaseProviderConnection,
                      info: TableInfo) -> Optional[str]:
    scale_x, scale_y = info.scale or (None, None)
    srid = info.raster_srid
    if scale_x is None or scale_y is None:
        rows = make_query(connection, f'''
            SELECT ST_PixelWidth({quote_identifier(info.raster_column)}),
                   ST_PixelHeight({quote_identifier(info.raster_column)}),
                   ST_SRID({quote_identifier(info.raster_column)})
            FROM {info.qualified_name()}
            WHERE {quote_identifier(info.raster_column)} IS NOT NULL
            LIMIT 1;
        ''')
        if not rows or rows[0][0] is None:
            return None
        scale_x, scale_y, srid = rows[0]
    unit = srid_unit(connection, srid)
    text = f'{format_size(scale_x)} x {format_size(scale_y)}'
    return f'{text} {unit}'.strip()


def details_rows(connection: QgsAbstractDatabaseProviderConnection,
                 info: TableInfo) -> Dict[str, List[Tuple[str, str]]]:
    details = {}
    comment = table_comment(connection, info)
    if comment:
        details['comment'] = [('', comment)]
    if info.estimated_rows is not None and info.estimated_rows >= 0:
        details['rows'] = [('', str(info.estimated_rows))]
    key = primary_key(connection, info)
    if key:
        details['primary_key'] = [('', key)]
    if info.geometry_columns:
        details['geometry'] = [
            (column, f'{geometry_type}, SRID {srid}, {dimension}D')
            for column, geometry_type, srid, dimension
            in info.geometry_columns]
    if info.is_raster():
        details['raster'] = [
            (info.raster_column, f'SRID {info.raster_srid}'),
            ('bands', f'{info.num_bands} ({pixel_types_label(info)})'),
        ]
        resolution = raster_resolution(connection, info)
        if resolution:
            details['raster'].append(('scale', resolution))
        if info.block_size and None not in info.block_size:
            details['raster'].append(
                ('block_size',
                 f'{info.block_size[0]} x {info.block_size[1]}'))
        if info.overviews:
            details['overviews'] = [
                (f'1:{factor}', qualified_name(schema, table))
                for schema, table, factor in info.overviews]
    details['columns'] = table_columns(connection, info)
    details['indexes'] = table_indexes(connection, info)
    return details
