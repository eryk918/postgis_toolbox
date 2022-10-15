from ...utils import make_query, unpack_nested_lists, QSqlDatabase

get_postgis_version_query = 'SELECT PostGIS_Lib_Version();'
get_postgis_version_extended_query = 'SELECT PostGIS_Full_Version();'

create_schema_query = 'CREATE SCHEMA IF NOT EXISTS "{name}";'
create_db_query = 'CREATE DATABASE "{name}";'


def create_db(db: QSqlDatabase, name: str) -> bool:
    return True if unpack_nested_lists(
        make_query(db, create_db_query.format(name=name))) else False


def create_schema(db: QSqlDatabase, name: str) -> bool:
    return True if unpack_nested_lists(make_query(db, create_schema_query.format(name=name))) else False
