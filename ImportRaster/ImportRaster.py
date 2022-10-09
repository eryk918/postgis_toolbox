# -*- coding: utf-8 -*-
import os
import tempfile
from os import listdir
from os.path import join, isfile
from typing import List

import processing
from qgis.PyQt.QtCore import QByteArray
from qgis.core import QgsCoordinateReferenceSystem, QgsTask, QgsRasterLayer, \
    Qgis
from qgis.gui import QgsProjectionSelectionDialog

from .UI.import_raster_ui import ImportRaster_UI
from .utils.raster_utils import make_sql_create_table, \
    make_sql_create_gist, create_raster_overviews, make_sql_addrastercolumn, \
    make_sql_insert_raster
from ..utils import project, iface, repair_path_for_exec, make_queries, \
    make_query, tr, add_rasters_to_project, create_postgis_raster_layer, \
    clean_after_analysis, change_alg_progress, RASTERS_LAYERS_GROUP


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
        for var_name, value in params.items():
            if isinstance(value, str):
                exec(repair_path_for_exec(f"self.{var_name} = '{value}'"))
            else:
                exec(f"self.{var_name} = {value}")
        self.actual_crs = project.crs().postgisSrid()

    def run(self):
        self.last_progress_value = 0
        self.temp_dir = tempfile.mkdtemp()
        raster_layer = QgsRasterLayer(self.input_file, "base")
        srid = raster_layer.crs().postgisSrid()
        if srid == 0 or srid == '':
            crs = QgsCoordinateReferenceSystem()
            selection_dialog = QgsProjectionSelectionDialog(iface.mainWindow())
            selection_dialog.setCrs(crs)
            if selection_dialog.exec():
                srid = selection_dialog.crs().postgisSrid()
        del raster_layer
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)

        if self.q_make_tiles:
            raster_list = self.make_tiles(
                self.input_file, srid, self.tile_width, self.tile_height)
        else:
            raster_list = [self.input_file]

        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 24)

        if self.cancel_detection():
            return False

        self.raster_insert(
            raster_list, srid, self.destination_table, self.destination_schema)

        if self.cancel_detection():
            return False

        if self.q_pyramids:
            create_raster_overviews(
                self.main.db, self.destination_schema,
                self.destination_table, 'rast', self.checked_overview, self,
                20)
        else:
            self.last_progress_value = \
                change_alg_progress(self, self.last_progress_value, 20)

        if self.cancel_detection():
            return False

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
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)
        clean_after_analysis(self)
        return True

    def make_tiles(self, raster_filepath: str, srid: int,
                   tile_size_x: int, tile_size_y: int) -> List[str]:
        processing.run(
            "gdal:retile",
            {
                'INPUT': [raster_filepath],
                'TILE_SIZE_X': tile_size_x, 'TILE_SIZE_Y': tile_size_y,
                'OVERLAP': 0, 'LEVELS': 1,
                'SOURCE_CRS': srid, 'RESAMPLING': 0,
                'DELIMITER': ';', 'OPTIONS': '',
                'EXTRA': '', 'DATA_TYPE': 5,
                'ONLY_PYRAMIDS': False,
                'DIR_FOR_ROW': False,
                'OUTPUT': self.temp_dir
            })
        return [join(self.temp_dir, file) for file in listdir(self.temp_dir)
                if isfile(join(self.temp_dir, file))]

    def raster_insert(self, raster_list: List[str], srid: int,
                      destination_table: str, destination_schema: str) -> bool:
        make_query(self.main.db,
                   make_sql_create_table(destination_table),
                   destination_schema)
        make_query(self.main.db,
                   make_sql_create_gist(destination_table, destination_table),
                   destination_schema)

        query_list = []
        for file_path in raster_list:
            with open(file_path, 'rb') as raster_file:
                query_list.append(
                    (
                        make_sql_insert_raster(
                            destination_table,
                            destination_schema,
                            srid
                        ),
                        QByteArray(raster_file.read())
                    )
                )
                if self.cancel_detection():
                    return False
                self.last_progress_value = \
                    change_alg_progress(self, self.last_progress_value,
                                        32 / len(raster_list))
        make_queries(
            query_list, self.main.db, destination_schema, True, True, self, 20)
        make_query(
            self.main.db,
            make_sql_addrastercolumn(destination_table, destination_schema),
            destination_schema)
        del query_list
        return True

    def finished(self, result: bool or str) -> str:
        if not result:
            iface.messageBar().pushMessage(
                tr('An error occurred while importing the raster.'),
                Qgis.Critical,
                3)
        elif result == 'canceled':
            iface.messageBar().pushMessage(
                tr('The import was aborted by the user.'),
                Qgis.Info,
                3)
        else:
            iface.messageBar().pushMessage(
                tr('The raster import has been completed successfully.'),
                Qgis.Success,
                3)

    def cancel_detection(self) -> bool:
        if self.isCanceled():
            clean_after_analysis(self)
            return True
        return False

    def cancel(self):
        super().cancel()
