# -*- coding: utf-8 -*-
import os

from qgis.core import QgsTask, Qgis

from .UI.import_raster_ui import ImportRaster_UI
from .utils.raster_utils import make_sql_create_raster_table, \
    make_sql_create_raster_gist, create_raster_overviews, \
    make_sql_add_raster_constraints, make_sql_insert_rasters, \
    count_raster_tiles, iter_raster_tiles, iter_whole_raster, \
    iter_tile_batches, \
    log_raster_table_info, drop_raster_table, ensure_gdal_drivers
from ..utils import project, iface, make_query, tr, add_rasters_to_project, \
    create_postgis_raster_layer, change_alg_progress, RASTERS_LAYERS_GROUP, \
    create_connection_from_uri, log


class ImportRaster:
    def __init__(self, parent):
        self.main = parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        self.actual_crs = project.crs().postgisSrid()
        self.plugin_dir = self.main.plugin_dir
        self.db = self.main.db

    def run(self) -> None:
        self.dlg = ImportRaster_UI(self)
        self.dlg.setup_dialog()
        self.dlg.run_dialog()


class RasterImporter(QgsTask):
    def __init__(self, desc, parent, params=None):
        QgsTask.__init__(self, desc)
        self.main = parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        for var_name, value in (params or {}).items():
            setattr(self, var_name, value)
        self.connection_uri = self.main.db.uri()
        self.actual_crs = project.crs().postgisSrid()
        self.imported = []
        self.failed = []
        self.last_progress_value = 0
        self.progress_scale = 1 / max(len(self.jobs), 1)

    def add_progress(self, value: float) -> None:
        self.last_progress_value = change_alg_progress(
            self, self.last_progress_value, value * self.progress_scale)

    def run(self) -> bool:
        self.connection = create_connection_from_uri(self.connection_uri)
        if not self.connection:
            return False
        if not ensure_gdal_drivers(self.connection):
            return False
        for job in self.jobs:
            if self.cancel_detection():
                return False
            for var_name, value in job.items():
                setattr(self, var_name, value)
            self.table_created = False
            if self.import_to_db():
                self.imported.append(job)
            else:
                if self.table_created:
                    drop_raster_table(
                        self.connection, self.destination_schema,
                        self.destination_table)
                if self.cancel_detection():
                    return False
                log(f'Import of {self.input_file} failed', Qgis.Warning)
                self.failed.append(job)
        self.setProgress(100)
        return bool(self.imported)

    def import_to_db(self) -> bool:
        self.add_progress(2)
        if not self.raster_insert() or self.cancel_detection():
            return False
        if self.q_pyramids:
            return create_raster_overviews(
                self.connection, self.destination_schema,
                self.destination_table, 'rast', self.checked_overview, self,
                24 * self.progress_scale)
        self.add_progress(24)
        return True

    def raster_insert(self) -> bool:
        schema, table = self.destination_schema, self.destination_table
        if self.q_overwrite and not drop_raster_table(
                self.connection, schema, table):
            return False
        if make_query(self.connection,
                      make_sql_create_raster_table(schema, table)) is None:
            return False
        self.table_created = True

        if self.q_make_tiles:
            tiles_amount = count_raster_tiles(
                self.input_file, self.tile_width, self.tile_height)
            tiles = iter_raster_tiles(
                self.input_file, self.tile_width, self.tile_height,
                self.q_compress)
        else:
            tiles_amount = 1
            tiles = iter_whole_raster(self.input_file)
        if not tiles_amount:
            return False

        for batch in iter_tile_batches(tiles):
            if make_query(self.connection, make_sql_insert_rasters(
                    schema, table, self.srid, batch)) is None:
                return False
            if self.cancel_detection():
                return False
            self.add_progress(70 * len(batch) / tiles_amount)

        if make_query(self.connection,
                      make_sql_create_raster_gist(schema, table)) is None:
            return False
        if make_query(self.connection,
                      make_sql_add_raster_constraints(schema, table)) is None:
            return False
        log_raster_table_info(self.connection, schema, table)
        self.add_progress(4)
        return True

    def finished(self, result: bool) -> None:
        if self.isCanceled():
            iface.messageBar().pushMessage(
                tr('The import was aborted by the user.'),
                Qgis.Info,
                3)
            return
        if self.imported and self.q_add_to_project:
            add_rasters_to_project(
                RASTERS_LAYERS_GROUP,
                [
                    create_postgis_raster_layer(
                        self.main.db,
                        self.destination_schema,
                        job['destination_table'],
                        job['layer_name']
                    ) for job in self.imported
                ],
                postgis_raster=True
            )
        if not result:
            iface.messageBar().pushMessage(
                tr('An error occurred while importing the raster.'),
                Qgis.Critical,
                3)
        elif self.failed:
            iface.messageBar().pushMessage(
                tr('Imported {0} of {1} rasters. Failed: {2}.').format(
                    len(self.imported), len(self.jobs),
                    ', '.join(job['layer_name'] for job in self.failed)),
                Qgis.Warning,
                8)
        elif len(self.imported) > 1:
            iface.messageBar().pushMessage(
                tr('{0} rasters have been imported successfully.').format(
                    len(self.imported)),
                Qgis.Success,
                3)
        else:
            iface.messageBar().pushMessage(
                tr('The raster import has been completed successfully.'),
                Qgis.Success,
                3)

    def cancel_detection(self) -> bool:
        return self.isCanceled()
