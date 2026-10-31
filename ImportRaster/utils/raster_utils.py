# -*- coding: utf-8 -*-
import math
from typing import Iterator, List, Optional
from uuid import uuid4

from osgeo import gdal
from qgis.core import Qgis, QgsAbstractDatabaseProviderConnection

from ...utils import make_query, change_alg_progress, log, quote_identifier, \
    quote_literal, qualified_name

raster_extensions = ['tif', 'tiff']

max_raster_untiled_size = 104857600

insert_batch_bytes = 16777216

tile_creation_options = ['COMPRESS=LZW']

enable_gdal_drivers_query = "SET postgis.gdal_enabled_drivers = 'ENABLE_ALL';"


def ensure_gdal_drivers(
        connection: QgsAbstractDatabaseProviderConnection) -> bool:
    rows = make_query(
        connection,
        "SELECT current_setting('postgis.gdal_enabled_drivers', true);")
    if rows is None:
        return False
    drivers = (rows[0][0] or '').split()
    if 'ENABLE_ALL' in drivers or 'GTiff' in drivers:
        return True
    return make_query(connection, enable_gdal_drivers_query) is not None


def open_raster_dataset(raster_path: str) -> Optional[gdal.Dataset]:
    dataset = gdal.Open(raster_path, gdal.GA_ReadOnly)
    if dataset is None:
        log(f'GDAL cannot open raster: {raster_path}', Qgis.Critical)
    return dataset


def count_raster_tiles(raster_path: str, tile_width: int,
                       tile_height: int) -> int:
    dataset = open_raster_dataset(raster_path)
    if dataset is None:
        return 0
    return math.ceil(dataset.RasterXSize / tile_width) * \
        math.ceil(dataset.RasterYSize / tile_height)


def read_vsimem_file(mem_path: str) -> bytes:
    stat = gdal.VSIStatL(mem_path)
    handle = gdal.VSIFOpenL(mem_path, 'rb')
    try:
        return gdal.VSIFReadL(1, stat.size, handle)
    finally:
        gdal.VSIFCloseL(handle)
        gdal.Unlink(mem_path)


def iter_raster_tiles(raster_path: str, tile_width: int,
                      tile_height: int,
                      compress: bool = True) -> Iterator[bytes]:
    dataset = open_raster_dataset(raster_path)
    if dataset is None:
        return
    x_size, y_size = dataset.RasterXSize, dataset.RasterYSize
    for y_offset in range(0, y_size, tile_height):
        for x_offset in range(0, x_size, tile_width):
            mem_path = f'/vsimem/{uuid4().hex}.tif'
            tile_dataset = gdal.Translate(
                mem_path, dataset, format='GTiff',
                creationOptions=tile_creation_options if compress else [],
                srcWin=[x_offset, y_offset,
                        min(tile_width, x_size - x_offset),
                        min(tile_height, y_size - y_offset)])
            if tile_dataset is None:
                log(f'GDAL cannot cut tile at {x_offset}, {y_offset} '
                    f'from {raster_path}', Qgis.Critical)
                return
            tile_dataset = None
            yield read_vsimem_file(mem_path)


def iter_whole_raster(raster_path: str) -> Iterator[bytes]:
    with open(raster_path, 'rb') as raster_file:
        yield raster_file.read()


def log_raster_table_info(connection: QgsAbstractDatabaseProviderConnection,
                          schema_name: str, table_name: str) -> None:
    rows = make_query(connection, f'''
        SELECT srid, num_bands, pixel_types, blocksize_x, blocksize_y,
            scale_x, scale_y
        FROM raster_columns
        WHERE r_table_schema = {quote_literal(schema_name)}
            AND r_table_name = {quote_literal(table_name)};
    ''')
    if rows:
        info = rows[0]
        log(f'{schema_name}.{table_name}: srid={info[0]}, bands={info[1]}, '
            f'pixel_types={info[2]}, blocksize={info[3]}x{info[4]}, '
            f'scale={info[5]}, {info[6]}')
    else:
        log(f'{schema_name}.{table_name}: no entry in raster_columns',
            Qgis.Warning)


def drop_raster_table(connection: QgsAbstractDatabaseProviderConnection,
                      schema_name: str, table_name: str) -> bool:
    overviews = make_query(connection, f'''
        SELECT o_table_schema, o_table_name
        FROM raster_overviews
        WHERE r_table_schema = {quote_literal(schema_name)}
            AND r_table_name = {quote_literal(table_name)};
    ''')
    if overviews is None:
        return False
    for overview_schema, overview_table in overviews:
        if make_query(connection, f'DROP TABLE IF EXISTS '
                      f'{qualified_name(overview_schema, overview_table)};'
                      ) is None:
            return False
    return make_query(connection, f'DROP TABLE IF EXISTS '
                      f'{qualified_name(schema_name, table_name)} CASCADE;'
                      ) is not None


def create_raster_overviews(
        connection: QgsAbstractDatabaseProviderConnection, schema_name: str,
        table_name: str, column: str = 'rast', levels=None, base_class=None,
        percent_amount: int = None) -> bool:
    if levels is None:
        levels = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
    for level in levels:
        overview_table = f'o_{level}_{table_name}'
        if base_class and base_class.cancel_detection():
            return False
        make_query(connection, f'DROP TABLE IF EXISTS '
                   f'{qualified_name(schema_name, overview_table)};')
        if make_query(connection, f'''
                SELECT ST_CreateOverview(
                    {quote_literal(qualified_name(schema_name, table_name))},
                    {quote_literal(column)}, {level}, 'Lanczos');
                ''') is None:
            return False
        make_query(connection, f'''
            ALTER TABLE {qualified_name(schema_name, overview_table)}
            ADD COLUMN rid bigserial PRIMARY KEY;
        ''')
        make_query(connection, make_sql_create_raster_gist(
            schema_name, overview_table, column))
        if base_class and base_class.cancel_detection():
            return False
        if base_class and percent_amount:
            base_class.last_progress_value = change_alg_progress(
                base_class, base_class.last_progress_value,
                percent_amount / len(levels))
    return True


def make_sql_create_raster_gist(schema: str, table: str,
                                column: str = 'rast') -> str:
    return f'''
        CREATE INDEX {quote_identifier(f'{table}_{column}_gist_idx')}
        ON {qualified_name(schema, table)}
        USING GIST (ST_ConvexHull({quote_identifier(column)}));
    '''


def make_sql_create_raster_table(schema: str, table: str,
                                 rast_column: str = 'rast') -> str:
    return f'''
        CREATE TABLE {qualified_name(schema, table)}
        ("rid" serial PRIMARY KEY, {quote_identifier(rast_column)} raster);
    '''


def make_sql_insert_rasters(schema: str, table: str, srid: int,
                            tiles: List[bytes],
                            rast_column: str = 'rast') -> str:
    values = ',\n'.join(
        f"(ST_FromGDALRaster('\\x{tile.hex()}'::bytea, {srid}))"
        for tile in tiles)
    return f'''
        INSERT INTO {qualified_name(schema, table)}
            ({quote_identifier(rast_column)})
        VALUES {values};
    '''


def iter_tile_batches(tiles: Iterator[bytes],
                      max_bytes: int = insert_batch_bytes
                      ) -> Iterator[List[bytes]]:
    batch, size = [], 0
    for tile in tiles:
        batch.append(tile)
        size += len(tile)
        if size >= max_bytes:
            yield batch
            batch, size = [], 0
    if batch:
        yield batch


def make_sql_add_raster_constraints(schema: str, table: str,
                                    rast_column: str = 'rast') -> str:
    return f'''
        SELECT AddRasterConstraints(
            {quote_literal(schema)}, {quote_literal(table)},
            {quote_literal(rast_column)},
            TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE, TRUE,
            TRUE, TRUE);
    '''
