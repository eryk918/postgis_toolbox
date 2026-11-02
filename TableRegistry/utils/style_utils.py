# -*- coding: utf-8 -*-
from typing import List, Optional, Tuple

from qgis.core import QgsAbstractDatabaseProviderConnection, QgsMapLayer, \
    QgsDataSourceUri

from .registry_utils import TableInfo
from ...utils import make_query, quote_literal

STYLE_TABLE = 'public.layer_styles'


def has_style_table(
        connection: QgsAbstractDatabaseProviderConnection) -> bool:
    rows = make_query(connection,
                      f"SELECT to_regclass({quote_literal(STYLE_TABLE)});")
    return bool(rows and rows[0][0])


def style_filter(info: TableInfo) -> str:
    return f'''
        f_table_schema = {quote_literal(info.schema)}
        AND f_table_name = {quote_literal(info.name)}
    '''


def table_styles(connection: QgsAbstractDatabaseProviderConnection,
                 info: TableInfo) -> List[Tuple]:
    if not has_style_table(connection):
        return []
    rows = make_query(connection, f'''
        SELECT id, stylename, f_geometry_column, useasdefault, owner,
               to_char(update_time, 'YYYY-MM-DD HH24:MI'), description,
               type
        FROM {STYLE_TABLE}
        WHERE {style_filter(info)}
        ORDER BY useasdefault DESC, stylename;
    ''')
    return [tuple(row) for row in rows or []]


def style_qml(connection: QgsAbstractDatabaseProviderConnection,
              style_id: int) -> Optional[str]:
    rows = make_query(connection, f'''
        SELECT styleqml FROM {STYLE_TABLE} WHERE id = {int(style_id)};
    ''')
    return rows[0][0] if rows else None


def set_default_style(connection: QgsAbstractDatabaseProviderConnection,
                      info: TableInfo, style_id: int,
                      geometry_column: str) -> bool:
    return make_query(connection, f'''
        UPDATE {STYLE_TABLE}
        SET useasdefault = (id = {int(style_id)})
        WHERE {style_filter(info)}
            AND f_geometry_column IS NOT DISTINCT FROM
                {quote_literal(geometry_column) if geometry_column else 'NULL'};
    ''') is not None


def rename_style(connection: QgsAbstractDatabaseProviderConnection,
                 style_id: int, name: str) -> bool:
    return make_query(connection, f'''
        UPDATE {STYLE_TABLE}
        SET stylename = {quote_literal(name)}
        WHERE id = {int(style_id)};
    ''') is not None


def delete_style(connection: QgsAbstractDatabaseProviderConnection,
                 style_id: int) -> bool:
    return make_query(connection, f'''
        DELETE FROM {STYLE_TABLE} WHERE id = {int(style_id)};
    ''') is not None


def layer_matches_table(layer: QgsMapLayer, info: TableInfo,
                        database: str) -> bool:
    if layer.providerType() not in ('postgres', 'postgresraster'):
        return False
    uri = QgsDataSourceUri(layer.source())
    return uri.schema() == info.schema and uri.table() == info.name \
        and (not uri.database() or uri.database() == database)
