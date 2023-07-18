# -*- coding: utf-8 -*-
import os

import processing
from qgis.core import QgsTask, Qgis

from .UI.import_vector_ui import ImportVector_UI
from .utils.vector_utils import none_geometry_types, \
    make_sql_set_geometry_srid, check_for_duplicate_id_column
from ..utils import project, iface, repair_path_for_exec, change_alg_progress, \
    clean_after_analysis, tr, add_vectors_to_project, \
    create_postgis_vector_layer, VECTORS_LAYERS_GROUP, make_query


class ImportVector:
    def __init__(self, parent):
        self.main = parent
        self.iface = iface
        self.project_path = os.path.dirname(
            os.path.abspath(project.fileName()))
        self.actual_crs = project.crs().postgisSrid()
        self.plugin_dir = self.main.plugin_dir
        self.db = self.main.db

    def run(self) -> None:
        self.dlg = ImportVector_UI(self)
        self.dlg.setup_dialog()
        self.dlg.run_dialog()


class VectorImporter(QgsTask):
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
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)
        if self.cancel_detection():
            return False

        self.vector_insert()
        if self.cancel_detection():
            return False

        if self.q_add_to_project:
            add_vectors_to_project(
                VECTORS_LAYERS_GROUP,
                [
                    create_postgis_vector_layer(
                        self.main.db,
                        self.destination_schema,
                        table,
                        layer_name=self.layer_names[
                            self.destination_tables.index(table)],
                        geom_col='geom'
                        if self.layer_types[self.destination_tables.index(
                            table)] not in none_geometry_types else ''
                    )
                    for table in self.destination_tables
                ]
            )
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)
        clean_after_analysis(self)
        return True

    def vector_insert(self) -> bool:
        for vector in self.input_files:
            processing.run(
                "qgis:importintopostgis",
                {
                    'INPUT': check_for_duplicate_id_column(vector),
                    'DATABASE': self.main.db.databaseName(),
                    'SCHEMA': self.destination_schema,
                    'TABLENAME': self.destination_tables[
                        self.input_files.index(vector)],
                    'PRIMARY_KEY': '',
                    'GEOMETRY_COLUMN': 'geom',
                    'ENCODING': 'UTF-8',
                    'OVERWRITE': self.q_overwrite,
                    'CREATEINDEX': self.q_create_index,
                    'LOWERCASE_NAMES': self.q_lower_case,
                    'DROP_STRING_LENGTH': self.q_drop_length,
                    'FORCE_SINGLEPART': self.q_force_singlepart
                }
            )
            make_query(
                self.main.db,
                make_sql_set_geometry_srid(
                    self.destination_tables[self.input_files.index(vector)],
                    self.destination_schema,
                    vector
                ),
                self.destination_schema
            )
            if self.cancel_detection():
                return False
            self.last_progress_value = change_alg_progress(
                self,
                self.last_progress_value,
                96 / len(self.input_files)
            )
        return True

    def finished(self, result: bool or str) -> None:
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
                tr('The vector import has been completed successfully.'),
                Qgis.Success,
                3)

    def cancel_detection(self) -> bool:
        if self.isCanceled():
            clean_after_analysis(self)
            return True
        return False

    def cancel(self):
        super().cancel()
