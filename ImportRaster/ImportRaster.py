# -*- coding: utf-8 -*-
import os

from qgis.core import QgsTask, Qgis

from .UI.import_raster_ui import ImportRaster_UI
from .utils.raster_utils import make_sql_create_raster_table, \
    make_sql_create_raster_gist, create_raster_overviews, \
    make_sql_add_raster_constraints, make_sql_insert_raster, \
    count_raster_tiles, iter_raster_tiles, iter_whole_raster, \
    log_raster_table_info, drop_raster_table
from ..utils import project, iface, make_query, tr, add_rasters_to_project, \
    create_postgis_raster_layer, change_alg_progress, RASTERS_LAYERS_GROUP, \
    create_connection_from_uri


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

    def run(self) -> bool:
        self.last_progress_value = 0
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)
        if self.cancel_detection():
            return False
        self.connection = create_connection_from_uri(self.connection_uri)
        self.table_created = False
        if not self.connection:
            return False
        if not self.import_to_db():
            if self.table_created:
                drop_raster_table(
                    self.connection, self.destination_schema,
                    self.destination_table)
            return False
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 100)
        return True

    def import_to_db(self) -> bool:
        if not self.raster_insert() or self.cancel_detection():
            return False
        if self.q_pyramids:
            return create_raster_overviews(
                self.connection, self.destination_schema,
                self.destination_table, 'rast', self.checked_overview, self,
                20)
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 20)
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
                self.input_file, self.tile_width, self.tile_height)
        else:
            tiles_amount = 1
            tiles = iter_whole_raster(self.input_file)
        if not tiles_amount:
            return False

        for tile in tiles:
            if make_query(self.connection, make_sql_insert_raster(
                    schema, table, self.srid, tile)) is None:
                return False
            if self.cancel_detection():
                return False
            self.last_progress_value = change_alg_progress(
                self, self.last_progress_value, 70 / tiles_amount)

        if make_query(self.connection,
                      make_sql_create_raster_gist(schema, table)) is None:
            return False
        if make_query(self.connection,
                      make_sql_add_raster_constraints(schema, table)) is None:
            return False
        log_raster_table_info(self.connection, schema, table)
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 4)
        return True

    def finished(self, result: bool) -> None:
        if self.isCanceled():
            iface.messageBar().pushMessage(
                tr('The import was aborted by the user.'),
                Qgis.Info,
                3)
        elif not result:
            iface.messageBar().pushMessage(
                tr('An error occurred while importing the raster.'),
                Qgis.Critical,
                3)
        else:
            if self.q_add_to_project:
                add_rasters_to_project(
                    RASTERS_LAYERS_GROUP,
                    [
                        create_postgis_raster_layer(
                            self.main.db,
                            self.destination_schema,
                            self.destination_table,
                            self.layer_name
                        )
                    ],
                    postgis_raster=True
                )
            iface.messageBar().pushMessage(
                tr('The raster import has been completed successfully.'),
                Qgis.Success,
                3)

    def cancel_detection(self) -> bool:
        return self.isCanceled()
