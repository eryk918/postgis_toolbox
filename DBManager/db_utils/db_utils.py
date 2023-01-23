from qgis.PyQt.QtCore import QSettings
from qgis._core import QgsDataSourceUri

from ...utils import make_query, QSqlDatabase, make_queries, tr

get_postgis_version_query = 'SELECT PostGIS_Lib_Version();'
get_postgis_version_extended_query = 'SELECT PostGIS_Full_Version();'

create_schema_query = 'CREATE SCHEMA IF NOT EXISTS "{name}";'
alter_schema_query = 'ALTER SCHEMA "{old_name}" RENAME TO "{name}";'
drop_schema_query = 'DROP SCHEMA IF EXISTS "{name}";'
create_db_query = 'CREATE DATABASE "{name}";'
alter_db_query = 'ALTER DATABASE "{old_name}" RENAME TO "{name}";'
drop_db_query = 'DROP DATABASE IF EXISTS "{name}";'
create_postgis_vector_query = 'CREATE EXTENSION IF NOT EXISTS postgis;'
create_postgis_raster_query = 'CREATE EXTENSION IF NOT EXISTS postgis_raster;'

terminate_users_query = """SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = '{0}'
                            AND pid <> pg_backend_pid();"""
get_dbs_query = '''SELECT datname 
                   FROM pg_database 
                   WHERE datistemplate = false;'''

ssl_modes = {
    tr('disable'):  'SslDisable',
    tr('allow'):  'SslAllow',
    tr('prefer'):  'SslPrefer',
    tr('require'):  'SslRequire',
    tr('verify-ca'): 'SslVerifyCa',
    tr('verity-full'): 'SslVerifyFull'
}

ssl_modes_enum = {
    QgsDataSourceUri.SslDisable: tr('disable'),
    QgsDataSourceUri.SslAllow: tr('allow'),
    QgsDataSourceUri.SslPrefer: tr('prefer'),
    QgsDataSourceUri.SslRequire: tr('require'),
    QgsDataSourceUri.SslVerifyCa: tr('verify-ca'),
    QgsDataSourceUri.SslVerifyFull: tr('verity-full')
}


def create_db(db: QSqlDatabase, name: str) -> None:
    make_query(db, create_db_query.format(name=name))
    db.setDatabaseName(name)
    db.open()
    make_queries(db,
                 [create_postgis_vector_query, create_postgis_raster_query])


def create_schema(db: QSqlDatabase, name: str) -> None:
    make_query(db, create_schema_query.format(name=name))


def alter_db(db: QSqlDatabase, old_name: str, new_name: str) -> None:
    make_query(db, terminate_users_query.format(old_name))
    db.setDatabaseName('postgres')
    db.open()
    make_query(db, alter_db_query.format(old_name=old_name, name=new_name))
    db.setDatabaseName(new_name)


def alter_schema(db: QSqlDatabase, old_name: str, new_name: str) -> None:
    make_query(db, alter_schema_query.format(old_name=old_name, name=new_name))


def remove_db(db: QSqlDatabase, name: str) -> None:
    make_query(db, terminate_users_query.format(name))
    db_name = db.databaseName()
    db.setDatabaseName('postgres')
    db.open()
    make_query(db, drop_db_query.format(name=name))
    db.setDatabaseName(db_name)


def remove_schema(db: QSqlDatabase, name: str) -> None:
    make_query(db, drop_schema_query.format(name=name))


def set_postgis_connection_processing(db: QSqlDatabase) -> bool:
    connection_dict = {
        'service': '',
        'host': db.hostName(),
        'port': db.port(),
        'database': db.databaseName(),
        'username': db.userName(),
        'password': db.password(),
        'authcfg': None,
        'publicOnly': False,
        'geometryColumnsOnly': False,
        'dontResolveType': False,
        'allowGeometrylessTables': True,
        'sslmode': 1,
        'savePassword': True,
        'saveUsername': True,
        'estimatedMetadata': False,
        'projectsInDatabase': False,
    }
    base_group_name = 'PostgreSQL/connections'
    settings_object = QSettings()
    settings_object.beginGroup(base_group_name)
    if db.databaseName() not in settings_object.childGroups():
        settings_object = QSettings()
        settings_object.beginGroup(
            f"{base_group_name}/{db.databaseName()}")
        for key, value in connection_dict.items():
            settings_object.setValue(key, value)
        settings_object.endGroup()
        return True
    else:
        return False


def remove_postgis_connection_processing(db: QSqlDatabase) -> bool:
    base_group_name = 'PostgreSQL/connections'
    settings_object = QSettings()
    settings_object.beginGroup(base_group_name)
    if db and db.databaseName() in settings_object.childGroups():
        settings_object.remove(db.databaseName())
    return False
