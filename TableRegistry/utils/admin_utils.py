# -*- coding: utf-8 -*-
from typing import List, Optional, Set, Tuple

from qgis.core import QgsAbstractDatabaseProviderConnection

from .registry_utils import TableInfo
from ...ImportRaster.utils.raster_utils import create_raster_overviews, \
    make_sql_add_raster_constraints, make_sql_create_raster_gist
from ...utils import make_query, quote_literal, quote_identifier, \
    qualified_name

TABLE_PRIVILEGES = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                    'REFERENCES', 'TRIGGER']
GEOMETRY_TYPES = ['POINT', 'MULTIPOINT', 'LINESTRING', 'MULTILINESTRING',
                  'POLYGON', 'MULTIPOLYGON', 'GEOMETRY']
OVERVIEW_LIMITS = [8, 32, 256, 2048]
TILE_SIZES = [64, 128, 256, 512]
INVALID_LIMIT = 100


def regclass(info: TableInfo) -> str:
    return f'{quote_literal(info.qualified_name())}::regclass'


def table_size(connection: QgsAbstractDatabaseProviderConnection,
               info: TableInfo) -> Optional[str]:
    rows = make_query(connection, f'''
        SELECT pg_size_pretty(pg_total_relation_size({regclass(info)}));
    ''')
    return rows[0][0] if rows else None


def table_maintenance(connection: QgsAbstractDatabaseProviderConnection,
                      info: TableInfo) -> List[Tuple[str, str]]:
    rows = make_query(connection, f'''
        SELECT to_char(GREATEST(last_vacuum, last_autovacuum),
                       'YYYY-MM-DD HH24:MI'),
               to_char(GREATEST(last_analyze, last_autoanalyze),
                       'YYYY-MM-DD HH24:MI'),
               n_live_tup, n_dead_tup
        FROM pg_stat_user_tables
        WHERE schemaname = {quote_literal(info.schema)}
            AND relname = {quote_literal(info.name)};
    ''')
    if not rows:
        return []
    vacuum, analyze, live, dead = rows[0]
    return [('last_vacuum', vacuum or '-'), ('last_analyze', analyze or '-'),
            ('dead_rows', str(dead))]


def table_owner(connection: QgsAbstractDatabaseProviderConnection,
                info: TableInfo) -> Optional[str]:
    rows = make_query(connection, f'''
        SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE oid = {regclass(info)};
    ''')
    return rows[0][0] if rows else None


def table_privileges(connection: QgsAbstractDatabaseProviderConnection,
                     info: TableInfo) -> List[Tuple[str, str]]:
    rows = make_query(connection, f'''
        SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC'
                    ELSE pg_get_userbyid(a.grantee) END,
               string_agg(a.privilege_type, ', ' ORDER BY a.privilege_type)
        FROM pg_class c, aclexplode(c.relacl) a
        WHERE c.oid = {regclass(info)}
        GROUP BY 1
        ORDER BY 1;
    ''')
    return [(row[0], row[1]) for row in rows or []]


def role_privileges(connection: QgsAbstractDatabaseProviderConnection,
                    info: TableInfo, role: str) -> Set[str]:
    grantee = '0' if role == 'PUBLIC' else \
        f'{quote_literal(role)}::regrole::oid'
    rows = make_query(connection, f'''
        SELECT a.privilege_type
        FROM pg_class c, aclexplode(c.relacl) a
        WHERE c.oid = {regclass(info)} AND a.grantee = {grantee};
    ''')
    return {row[0] for row in rows or []}


def role_names(connection: QgsAbstractDatabaseProviderConnection) -> List[str]:
    rows = make_query(connection, '''
        SELECT rolname FROM pg_roles
        WHERE position('pg_' IN rolname) <> 1
        ORDER BY rolname;
    ''')
    return [row[0] for row in rows or []]


def count_rows(connection: QgsAbstractDatabaseProviderConnection,
               info: TableInfo) -> Optional[int]:
    rows = make_query(connection,
                      f'SELECT count(*) FROM {info.qualified_name()};')
    return rows[0][0] if rows else None


def has_spatial_index(connection: QgsAbstractDatabaseProviderConnection,
                      info: TableInfo, column: str) -> bool:
    rows = make_query(connection, f'''
        SELECT 1
        FROM pg_index i
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN pg_am am ON am.oid = ic.relam
        WHERE i.indrelid = {regclass(info)} AND am.amname = 'gist'
            AND pg_get_indexdef(i.indexrelid) LIKE
                {quote_literal(f'%{quote_identifier(column)}%')};
    ''')
    return bool(rows)


def column_names(connection: QgsAbstractDatabaseProviderConnection,
                 info: TableInfo) -> List[str]:
    rows = make_query(connection, f'''
        SELECT attname FROM pg_attribute
        WHERE attrelid = {regclass(info)} AND attnum > 0 AND NOT attisdropped;
    ''')
    return [row[0] for row in rows or []]


def primary_key_columns(connection: QgsAbstractDatabaseProviderConnection,
                        info: TableInfo) -> List[str]:
    rows = make_query(connection, f'''
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
            ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = {regclass(info)} AND i.indisprimary
        ORDER BY a.attnum;
    ''')
    return [row[0] for row in rows or []]


def invalid_geometries(connection: QgsAbstractDatabaseProviderConnection,
                       info: TableInfo,
                       column: str) -> Tuple[Optional[int], List[Tuple[str, str]]]:
    keys = primary_key_columns(connection, info)
    key = quote_identifier(keys[0]) if len(keys) == 1 else 'ctid'
    geometry = quote_identifier(column)
    count = make_query(connection, f'''
        SELECT count(*) FROM {info.qualified_name()}
        WHERE NOT ST_IsValid({geometry});
    ''')
    if not count:
        return None, []
    rows = make_query(connection, f'''
        SELECT {key}::text, ST_IsValidReason({geometry})
        FROM {info.qualified_name()}
        WHERE NOT ST_IsValid({geometry})
        LIMIT {INVALID_LIMIT};
    ''')
    return count[0][0], [(row[0], row[1]) for row in rows or []]


def vacuum_progress_sql(info: TableInfo) -> str:
    return f'''
        SELECT heap_blks_scanned, heap_blks_total
        FROM pg_stat_progress_vacuum
        WHERE relid = {regclass(info)};
    '''


def index_progress_sql(info: TableInfo) -> str:
    return f'''
        SELECT CASE WHEN blocks_total > 0 THEN blocks_done ELSE tuples_done END,
               CASE WHEN blocks_total > 0 THEN blocks_total ELSE tuples_total END
        FROM pg_stat_progress_create_index
        WHERE relid = {regclass(info)};
    '''


def vacuum_analyze(connection: QgsAbstractDatabaseProviderConnection,
                   info: TableInfo) -> bool:
    return make_query(
        connection, f'VACUUM ANALYZE {info.qualified_name()};') is not None


def create_spatial_index(connection: QgsAbstractDatabaseProviderConnection,
                         info: TableInfo, column: str) -> bool:
    if info.is_raster():
        sql = make_sql_create_raster_gist(info.schema, info.name, column)
    else:
        sql = f'''
            CREATE INDEX {quote_identifier(f'{info.name}_{column}_idx')}
            ON {info.qualified_name()}
            USING GIST ({quote_identifier(column)});
        '''
    return make_query(connection, sql) is not None


def add_primary_key(connection: QgsAbstractDatabaseProviderConnection,
                    info: TableInfo) -> Optional[str]:
    columns = column_names(connection, info)
    column = 'id' if 'id' not in columns else 'pk_id'
    result = make_query(connection, f'''
        ALTER TABLE {info.qualified_name()}
        ADD COLUMN {quote_identifier(column)} bigserial PRIMARY KEY;
    ''')
    return column if result is not None else None


def refresh_materialized_view(
        connection: QgsAbstractDatabaseProviderConnection,
        info: TableInfo) -> bool:
    return make_query(
        connection,
        f'REFRESH MATERIALIZED VIEW {info.qualified_name()};') is not None


def relocate_sql(info: TableInfo, schema: str, name: str) -> str:
    statements = []
    if schema != info.schema:
        statements.append(
            f'ALTER {info.keyword()} {info.qualified_name()} '
            f'SET SCHEMA {quote_identifier(schema)};')
    if name != info.name:
        statements.append(
            f'ALTER {info.keyword()} {qualified_name(schema, info.name)} '
            f'RENAME TO {quote_identifier(name)};')
    for overview_schema, table, factor in info.overviews:
        new_overview = f'o_{factor}_{name}'
        statements.append(f'''
            SELECT DropOverviewConstraints(
                {quote_literal(overview_schema)}, {quote_literal(table)},
                {quote_literal(info.raster_column)});
            ALTER TABLE {qualified_name(overview_schema, table)}
            SET SCHEMA {quote_identifier(schema)};
            ALTER TABLE {qualified_name(schema, table)}
            RENAME TO {quote_identifier(new_overview)};
            SELECT AddOverviewConstraints(
                {quote_literal(schema)}, {quote_literal(new_overview)},
                {quote_literal(info.raster_column)},
                {quote_literal(schema)}, {quote_literal(name)},
                {quote_literal(info.raster_column)}, {factor});
        ''' if overview_schema != schema else f'''
            SELECT DropOverviewConstraints(
                {quote_literal(overview_schema)}, {quote_literal(table)},
                {quote_literal(info.raster_column)});
            ALTER TABLE {qualified_name(overview_schema, table)}
            RENAME TO {quote_identifier(new_overview)};
            SELECT AddOverviewConstraints(
                {quote_literal(schema)}, {quote_literal(new_overview)},
                {quote_literal(info.raster_column)},
                {quote_literal(schema)}, {quote_literal(name)},
                {quote_literal(info.raster_column)}, {factor});
        ''')
    return '\n'.join(statements)


def relocate_table(connection: QgsAbstractDatabaseProviderConnection,
                   info: TableInfo, schema: str, name: str) -> bool:
    sql = relocate_sql(info, schema, name)
    if not sql:
        return True
    return make_query(connection, sql) is not None


def copy_table(connection: QgsAbstractDatabaseProviderConnection,
               info: TableInfo, schema: str, name: str) -> bool:
    target = qualified_name(schema, name)
    if info.relkind in ('r', 'p'):
        sql = f'''
            CREATE TABLE {target} (LIKE {info.qualified_name()} INCLUDING ALL);
            INSERT INTO {target} SELECT * FROM {info.qualified_name()};
        '''
    else:
        sql = f'CREATE TABLE {target} AS SELECT * FROM {info.qualified_name()};'
    return make_query(connection, sql) is not None


def update_srid(connection: QgsAbstractDatabaseProviderConnection,
                info: TableInfo, column: str, srid: int) -> bool:
    return make_query(connection, f'''
        SELECT UpdateGeometrySRID(
            {quote_literal(info.schema)}, {quote_literal(info.name)},
            {quote_literal(column)}, {int(srid)});
    ''') is not None


def force_geometry_type(connection: QgsAbstractDatabaseProviderConnection,
                        info: TableInfo, column: str, geometry_type: str,
                        srid: int) -> bool:
    geometry = quote_identifier(column)
    using = f'ST_Multi({geometry})' if geometry_type.startswith('MULTI') \
        else geometry
    return make_query(connection, f'''
        ALTER TABLE {info.qualified_name()}
        ALTER COLUMN {geometry}
        TYPE geometry({geometry_type}, {int(srid)})
        USING {using};
    ''') is not None


def build_overviews(connection: QgsAbstractDatabaseProviderConnection,
                    info: TableInfo, max_level: int) -> bool:
    levels = [level for level in [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                                  2048] if level <= max_level]
    for schema, table, _ in info.overviews:
        if make_query(connection,
                      f'DROP TABLE IF EXISTS {qualified_name(schema, table)};'
                      ) is None:
            return False
    return create_raster_overviews(
        connection, info.schema, info.name, info.raster_column, levels)


def add_raster_constraints(connection: QgsAbstractDatabaseProviderConnection,
                           info: TableInfo) -> bool:
    return make_query(connection, make_sql_add_raster_constraints(
        info.schema, info.name, info.raster_column)) is not None


def retile(connection: QgsAbstractDatabaseProviderConnection,
           info: TableInfo, tile_size: int, name: str) -> bool:
    target = qualified_name(info.schema, name)
    column = quote_identifier(info.raster_column)
    sql = f'''
        CREATE TABLE {target} ("rid" serial PRIMARY KEY, {column} raster);
        INSERT INTO {target} ({column})
        SELECT ST_Tile(ST_Union({column}), {tile_size}, {tile_size})
        FROM {info.qualified_name()};
        {make_sql_create_raster_gist(info.schema, name, info.raster_column)}
        {make_sql_add_raster_constraints(info.schema, name, info.raster_column)}
    '''
    return make_query(connection, sql) is not None


def role_sql(role: str) -> str:
    return 'PUBLIC' if role == 'PUBLIC' else quote_identifier(role)


def apply_privileges(connection: QgsAbstractDatabaseProviderConnection,
                     info: TableInfo, role: str, grant: List[str],
                     revoke: List[str]) -> bool:
    statements = []
    if grant:
        statements.append(
            f'GRANT {", ".join(grant)} ON {info.qualified_name()} '
            f'TO {role_sql(role)};')
    if revoke:
        statements.append(
            f'REVOKE {", ".join(revoke)} ON {info.qualified_name()} '
            f'FROM {role_sql(role)};')
    if not statements:
        return True
    return make_query(connection, '\n'.join(statements)) is not None


def change_owner(connection: QgsAbstractDatabaseProviderConnection,
                 info: TableInfo, role: str) -> bool:
    return make_query(connection, f'''
        ALTER {info.keyword()} {info.qualified_name()}
        OWNER TO {quote_identifier(role)};
    ''') is not None
