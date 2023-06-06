# -*- coding: utf-8 -*-

from ...utils import QSqlDatabase, QApplication, make_query, \
    change_alg_progress

raster_extensions = ['tif', 'tiff']

max_raster_untiled_size = 104857600


def create_raster_overviews(db: QSqlDatabase, schema_name: str,
                            table_name: str, column: str = 'rast',
                            levels=None, base_class=None,
                            percent_amount: int = None) -> bool:
    if levels is None:
        levels = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
    for level in levels:
        overview_tablename = f'o_{level}_{table_name}'
        full_table_name = f'''"{schema_name}"."{overview_tablename}"'''
        correct_name = \
            f'''"{schema_name.replace('"', '')}"."{table_name.replace('"', '')}"'''

        make_query(db,
                   f'''DROP TABLE IF EXISTS 
                            {full_table_name};''',
                   schema_name)

        if base_class and hasattr(base_class, 'cancel_detection'):
            if base_class.cancel_detection():
                return False

        make_query(db,
                   f"""
                        SELECT ST_CreateOverview(
                        '{correct_name}', '{column}', {level}, 'Lanczos');
                   """,
                   schema_name)
        make_query(db,
                   repair_overview_table(overview_tablename, schema_name),
                   schema_name)
        QApplication.processEvents()
        index_table = f'o_{str(level)}_{table_name}'
        make_query(db,
                   make_sql_create_gist(table_name, index_table, column),
                   schema_name)
        if base_class and hasattr(base_class, 'cancel_detection'):
            if base_class.cancel_detection():
                return False
        if base_class and hasattr(base_class, 'last_progress_value'):
            base_class.last_progress_value = \
                change_alg_progress(base_class, base_class.last_progress_value,
                                    percent_amount / len(levels))
    return True


def make_sql_create_gist(table: str, gist_table: str,
                         column: str = 'rast') -> str:
    sql = f'CREATE INDEX "{gist_table}_{column}_gist_idx" ON ' \
          f'{table} USING GIST (ST_CONVEXHULL({column}));'

    return sql


def make_sql_create_table(table: str, rast_column: str = 'rast') -> str:
    return f'CREATE TABLE "{table}" ' \
           f'("rid" serial PRIMARY KEY, "{rast_column}" raster);'


def make_sql_insert_raster(table: str, schema: str, srid: int,
                           rast_column: str = 'rast') -> str:
    return f'INSERT INTO {schema}."{table}" ({rast_column}) ' \
           f'VALUES (ST_FromGDALRaster(?, {srid}));'


def make_sql_addrastercolumn(table: str, schema: str,
                             rast_column: str = 'rast') -> str:
    return f"SELECT AddRasterConstraints('{schema}','{table}'," \
           f"'{rast_column}',TRUE,TRUE,TRUE,TRUE,TRUE,TRUE,FALSE,TRUE,TRUE," \
           f"TRUE,TRUE,TRUE);"


def repair_overview_table(table: str, schema: str) -> str:
    return f'ALTER TABLE {schema}."{table}" ADD COLUMN rid bigserial ' \
           f'PRIMARY KEY;'


def make_sql_vacuum(table: str, schema: str) -> str:
    return f'VACUUM ANALYZE {schema}."{table}";'
