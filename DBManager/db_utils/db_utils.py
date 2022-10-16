from ...utils import make_query, QSqlDatabase

get_postgis_version_query = 'SELECT PostGIS_Lib_Version();'
get_postgis_version_extended_query = 'SELECT PostGIS_Full_Version();'

create_schema_query = 'CREATE SCHEMA IF NOT EXISTS "{name}";'
alter_schema_query = 'ALTER SCHEMA "{old_name}" RENAME TO "{name}";'
drop_schema_query = 'DROP SCHEMA IF EXISTS "{name}";'
create_db_query = 'CREATE DATABASE "{name}";'
alter_db_query = 'ALTER DATABASE "{old_name}" RENAME TO "{name}";'
drop_db_query = 'DROP DATABASE IF EXISTS "{name}";'
create_postgis_query = 'CREATE EXTENSION postgis;'

terminate_users_query = """SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = '{0}'
                            AND pid <> pg_backend_pid();"""
get_dbs_query = '''SELECT datname 
                   FROM pg_database 
                   WHERE datistemplate = false;'''


def create_db(db: QSqlDatabase, name: str) -> None:
    make_query(db, create_db_query.format(name=name))
    db.setDatabaseName(name)
    db.open()
    make_query(db, create_postgis_query)


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
