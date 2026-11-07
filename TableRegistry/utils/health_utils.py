# -*- coding: utf-8 -*-
from typing import Dict, List, Optional, Tuple

from qgis.core import QgsAbstractDatabaseProviderConnection

from .registry_utils import EXCLUDED_SCHEMAS
from ...utils import make_query, quote_literal

HEALTH_CHECKS = ('no_primary_key', 'no_spatial_index', 'dead_rows',
                 'never_analyzed', 'unused_indexes', 'raster_no_constraints')

FIXABLE_CHECKS = ('no_primary_key', 'no_spatial_index', 'dead_rows',
                  'never_analyzed', 'raster_no_constraints')

DEAD_ROWS_MINIMUM = 1000

UNUSED_INDEX_MINIMUM_BYTES = 1048576


def excluded_schemas_sql() -> str:
    return ', '.join(quote_literal(name) for name in EXCLUDED_SCHEMAS)


def health_queries() -> Dict[str, str]:
    excluded = excluded_schemas_sql()
    return {
        'no_primary_key': f'''
            SELECT n.nspname, c.relname, ''
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p')
                AND n.nspname NOT IN ({excluded})
                AND NOT EXISTS (
                    SELECT 1 FROM pg_index i
                    WHERE i.indrelid = c.oid AND i.indisprimary)
            ORDER BY 1, 2;
        ''',
        'no_spatial_index': f'''
            SELECT g.f_table_schema, g.f_table_name, g.f_geometry_column
            FROM geometry_columns g
            JOIN pg_namespace n ON n.nspname = g.f_table_schema
            JOIN pg_class c
                ON c.relnamespace = n.oid AND c.relname = g.f_table_name
            WHERE c.relkind IN ('r', 'p', 'm')
                AND g.f_table_schema NOT IN ({excluded})
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_index i
                    JOIN pg_class ic ON ic.oid = i.indexrelid
                    JOIN pg_am am ON am.oid = ic.relam
                    WHERE i.indrelid = c.oid AND am.amname = 'gist'
                        AND pg_get_indexdef(i.indexrelid) LIKE
                            '%' || quote_ident(g.f_geometry_column) || '%')
            ORDER BY 1, 2, 3;
        ''',
        'dead_rows': f'''
            SELECT schemaname, relname,
                   n_dead_tup::text || ' / ' || n_live_tup::text
            FROM pg_stat_user_tables
            WHERE n_dead_tup > {DEAD_ROWS_MINIMUM}
                AND n_dead_tup > n_live_tup * 0.2
                AND schemaname NOT IN ({excluded})
            ORDER BY n_dead_tup DESC;
        ''',
        'never_analyzed': f'''
            SELECT schemaname, relname, n_live_tup::text
            FROM pg_stat_user_tables
            WHERE last_analyze IS NULL AND last_autoanalyze IS NULL
                AND n_live_tup > 0
                AND schemaname NOT IN ({excluded})
            ORDER BY n_live_tup DESC;
        ''',
        'unused_indexes': f'''
            SELECT s.schemaname, s.relname,
                   s.indexrelname || ' (' ||
                   pg_size_pretty(pg_relation_size(s.indexrelid)) || ')'
            FROM pg_stat_user_indexes s
            JOIN pg_index i ON i.indexrelid = s.indexrelid
            WHERE s.idx_scan = 0 AND NOT i.indisprimary AND NOT i.indisunique
                AND pg_relation_size(s.indexrelid) >
                    {UNUSED_INDEX_MINIMUM_BYTES}
                AND s.schemaname NOT IN ({excluded})
            ORDER BY pg_relation_size(s.indexrelid) DESC;
        ''',
        'raster_no_constraints': f'''
            SELECT r_table_schema, r_table_name, r_raster_column
            FROM raster_columns
            WHERE (srid = 0 OR scale_x IS NULL OR blocksize_x IS NULL
                   OR num_bands IS NULL)
                AND r_table_schema NOT IN ({excluded})
            ORDER BY 1, 2;
        ''',
    }


def has_raster_support(
        connection: QgsAbstractDatabaseProviderConnection) -> bool:
    rows = make_query(connection, "SELECT to_regclass('raster_columns');")
    return bool(rows and rows[0][0])


def run_health_check(
        connection: QgsAbstractDatabaseProviderConnection
) -> Optional[Dict[str, List[Tuple[str, str, str]]]]:
    queries = health_queries()
    if not has_raster_support(connection):
        queries.pop('raster_no_constraints')
    findings = {}
    for check, sql in queries.items():
        rows = make_query(connection, sql)
        if rows is None:
            return None
        findings[check] = [(row[0], row[1], row[2] or '') for row in rows]
    return findings
