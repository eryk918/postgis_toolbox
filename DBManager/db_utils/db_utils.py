from qgis.core import QgsDataSourceUri, QgsAbstractDatabaseProviderConnection

from ...utils import make_query, tr, quote_identifier, quote_literal, \
    connection_for_database, connection_uri

get_postgis_version_query = 'SELECT PostGIS_Lib_Version();'
get_postgis_version_extended_query = 'SELECT PostGIS_Full_Version();'
get_dbs_query = '''SELECT datname
                   FROM pg_database
                   WHERE datistemplate = false
                   ORDER BY datname;'''

ssl_modes = {
    tr('disable'): QgsDataSourceUri.SslDisable,
    tr('allow'): QgsDataSourceUri.SslAllow,
    tr('prefer'): QgsDataSourceUri.SslPrefer,
    tr('require'): QgsDataSourceUri.SslRequire,
    tr('verify-ca'): QgsDataSourceUri.SslVerifyCa,
    tr('verity-full'): QgsDataSourceUri.SslVerifyFull
}


def terminate_users_query(database_name: str) -> str:
    return f'''SELECT pg_terminate_backend(pg_stat_activity.pid)
               FROM pg_stat_activity
               WHERE pg_stat_activity.datname = {quote_literal(database_name)}
               AND pid <> pg_backend_pid();'''


def maintenance_connection(
        server_connection: QgsAbstractDatabaseProviderConnection,
        database_name: str) -> QgsAbstractDatabaseProviderConnection:
    if connection_uri(server_connection).database() == database_name:
        return connection_for_database(server_connection, 'postgres')
    return server_connection


def create_db(server_connection: QgsAbstractDatabaseProviderConnection,
              name: str) -> bool:
    if make_query(server_connection,
                  f'CREATE DATABASE {quote_identifier(name)};') is None:
        return False
    db_connection = connection_for_database(server_connection, name)
    if make_query(db_connection,
                  'CREATE EXTENSION IF NOT EXISTS postgis;') is None:
        return False
    make_query(db_connection, 'CREATE EXTENSION IF NOT EXISTS postgis_raster;')
    return True


def create_schema(connection: QgsAbstractDatabaseProviderConnection,
                  name: str) -> bool:
    return make_query(
        connection,
        f'CREATE SCHEMA IF NOT EXISTS {quote_identifier(name)};') is not None


def alter_db(server_connection: QgsAbstractDatabaseProviderConnection,
             old_name: str, new_name: str) -> bool:
    connection = maintenance_connection(server_connection, old_name)
    make_query(connection, terminate_users_query(old_name))
    return make_query(
        connection,
        f'ALTER DATABASE {quote_identifier(old_name)} '
        f'RENAME TO {quote_identifier(new_name)};') is not None


def alter_schema(connection: QgsAbstractDatabaseProviderConnection,
                 old_name: str, new_name: str) -> bool:
    return make_query(
        connection,
        f'ALTER SCHEMA {quote_identifier(old_name)} '
        f'RENAME TO {quote_identifier(new_name)};') is not None


def remove_db(server_connection: QgsAbstractDatabaseProviderConnection,
              name: str) -> bool:
    connection = maintenance_connection(server_connection, name)
    make_query(connection, terminate_users_query(name))
    return make_query(
        connection,
        f'DROP DATABASE IF EXISTS {quote_identifier(name)};') is not None


def remove_schema(connection: QgsAbstractDatabaseProviderConnection,
                  name: str) -> bool:
    return make_query(
        connection,
        f'DROP SCHEMA IF EXISTS {quote_identifier(name)} CASCADE;') is not None
