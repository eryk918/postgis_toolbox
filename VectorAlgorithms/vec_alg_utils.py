import re
from typing import List, Dict

import psycopg2
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtSql import QSqlDatabase
from qgis.core import QgsDataSourceUri, QgsCredentials

from ..utils import make_query, test_query, unpack_nested_lists, plugin_name, \
    main_window, tr


def get_pg_table_name_from_uri(uri: str) -> str:
    uri = uri.strip('"')
    regexp = re.compile(' table="([^"]*)"\\."([^"]*)"').search(uri)
    if regexp:
        return regexp.groups()[0] + '.' + regexp.groups()[1]
    return re.compile(' table="([^"]*)"').search(uri).groups()[0] \
        if regexp else 'NOT PG LAYER'


def get_pg_table_name_from_raster_uri(uri: str) -> Dict[str, str]:
    uri = uri.strip('"')
    result_dict = {}
    regexp_table = re.compile(' table=\'([^"]*)\'').search(uri)
    if regexp_table:
        result_dict['TABLE'] = regexp_table.groups()[0]
    regexp_schema = re.compile('schema=\'([^\']*)\'').search(uri)
    if regexp_schema:
        result_dict['SCHEMA'] = regexp_schema.groups()[0]
    return result_dict


def get_pg_name(layer):
    datasource_uri = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
    conninfo = datasource_uri.connectionInfo()
    conn = None
    ok = False
    while not conn:
        try:
            conn = psycopg2.connect(datasource_uri.connectionInfo())
        except psycopg2.OperationalError:
            (ok, user, passwd) = QgsCredentials.instance().get(
                conninfo,
                datasource_uri.username(),
                datasource_uri.password()
            )
            if not ok:
                break

            datasource_uri.setUsername(user)
            datasource_uri.setPassword(passwd)

    if not conn:
        raise RuntimeError(
            'Could not connect to PostgreSQL database - check connection info')
    if ok:
        QgsCredentials.instance().put(conninfo, user, passwd)

    return f"PG:{datasource_uri.connectionInfo()}", '"PostgreSQL"'


def get_table_geom_columns(
        db: QSqlDatabase, schema: str, table: str) -> List[str]:
    if db.isOpen() and db.isValid() and make_query(db, test_query):
        return unpack_nested_lists(
            make_query(
                db,
                f'''
                    SELECT f_geometry_column 
                    FROM geometry_columns 
                    WHERE f_table_schema = '{schema}' 
                        AND f_table_name = '{table}'; 
                '''
            )
        )
    return []


def get_table_columns(db: QSqlDatabase, schema: str, table: str,
                      excluded_cols: List[str]) -> List[str]:
    if not excluded_cols:
        excluded_cols = ['']
    if db.isOpen() and db.isValid() and make_query(db, test_query):
        return unpack_nested_lists(
            make_query(
                db,
                f'''
                    SELECT attname 
                    FROM pg_attribute 
                    WHERE attrelid = '"{schema}"."{table}"'::regclass 
                        AND NOT attisdropped 
                        AND attnum > 0 
                        AND attname NOT IN ('{"', '".join(excluded_cols)}') 
                    ORDER BY attnum
                '''
            )
        )
    return []


def create_vector_geom_index(
        db: QSqlDatabase, table: str, geom_col: str, schema: str = '') -> List[str]:
    if not geom_col:
        geom_col = 'geom'
    if db.isOpen() and db.isValid() and make_query(db, test_query):
        return unpack_nested_lists(
            make_query(
                db,
                f'''
                    CREATE INDEX "idx_{table}" ON {f'"{schema}".' if schema else ''}"{table}" 
                    USING GIST("{geom_col}");
                '''
            )
        )
    return []


def check_table_exists_in_schema(
        db: QSqlDatabase, schema: str, table: str) -> bool:
    if db.isOpen() and db.isValid() and make_query(db, test_query):
        return unpack_nested_lists(
            make_query(
                db,
                f'''
                    SELECT EXISTS (
                       SELECT FROM information_schema.tables 
                       WHERE  table_schema = '{schema}'
                       AND    table_name   = '{table}'
                    );
                '''
            )
        )[0]
    return False


def check_db_connection(parent: object, schemas_list_name: str) -> bool:
    if not hasattr(parent, schemas_list_name) or \
            not getattr(parent, schemas_list_name):
        QMessageBox.critical(
            main_window, plugin_name,
            tr('No active connection to the database was found.\n'
               'Use DB Manager and try again.'),
            QMessageBox.Ok)
        return False
    else:
        return True
