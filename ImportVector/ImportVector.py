# -*- coding: utf-8 -*-
import os

from qgis.core import QgsTask, Qgis, QgsVectorLayer, QgsDataSourceUri, \
    QgsVectorLayerExporter

from .UI.import_vector_ui import ImportVector_UI
from .utils.vector_utils import none_geometry_types, \
    check_for_duplicate_id_column
from ..utils import project, iface, change_alg_progress, clean_after_analysis, \
    tr, add_vectors_to_project, create_postgis_vector_layer, \
    VECTORS_LAYERS_GROUP, make_query, log, create_connection_from_uri, \
    qualified_name, quote_identifier


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
        if not self.connection:
            return False
        if not self.vector_insert() or self.cancel_detection():
            return False
        self.last_progress_value = \
            change_alg_progress(self, self.last_progress_value, 2)
        clean_after_analysis(self)
        return True

    def vector_insert(self) -> bool:
        for position, vector in enumerate(self.input_files):
            table_name = self.destination_tables[position]
            if not self.export_layer(vector, table_name):
                return False
            if self.cancel_detection():
                return False
            self.last_progress_value = change_alg_progress(
                self,
                self.last_progress_value,
                96 / len(self.input_files)
            )
        return True

    def export_layer(self, vector_path: str, table_name: str) -> bool:
        layer = QgsVectorLayer(
            check_for_duplicate_id_column(vector_path), table_name, 'ogr')
        if not layer.isValid():
            log(f'Invalid vector layer: {vector_path}', Qgis.Critical)
            return False
        layer.setProviderEncoding('UTF-8')
        geom_column = 'geom' \
            if layer.wkbType() not in none_geometry_types else ''
        uri = QgsDataSourceUri(self.connection_uri)
        uri.setDataSource(
            self.destination_schema, table_name, geom_column, '', 'id')
        options = {
            'overwrite': self.q_overwrite,
            'lowercaseFieldNames': self.q_lower_case,
            'dropStringConstraints': self.q_drop_length,
            'forceSinglePartGeometryType': self.q_force_singlepart
        }
        result, message = QgsVectorLayerExporter.exportLayer(
            layer, uri.uri(False), 'postgres', layer.crs(), False, options)
        if result != Qgis.VectorExportResult.Success:
            log(f'{message}\n{vector_path}', Qgis.Critical)
            return False
        if self.q_create_index and geom_column:
            make_query(self.connection, f'''
                CREATE INDEX {quote_identifier(f'{table_name}_{geom_column}_idx')}
                ON {qualified_name(self.destination_schema, table_name)}
                USING GIST ({quote_identifier(geom_column)});
            ''')
        return True

    def finished(self, result: bool) -> None:
        if self.isCanceled():
            iface.messageBar().pushMessage(
                tr('The import was aborted by the user.'),
                Qgis.Info,
                3)
        elif not result:
            iface.messageBar().pushMessage(
                tr('An error occurred while importing the vector.'),
                Qgis.Critical,
                3)
        else:
            if self.q_add_to_project:
                self.add_imported_layers()
            iface.messageBar().pushMessage(
                tr('The vector import has been completed successfully.'),
                Qgis.Success,
                3)

    def add_imported_layers(self) -> None:
        add_vectors_to_project(
            VECTORS_LAYERS_GROUP,
            [
                create_postgis_vector_layer(
                    self.main.db,
                    self.destination_schema,
                    table,
                    geom_col='geom'
                    if self.layer_types[position] not in none_geometry_types
                    else '',
                    layer_name=self.layer_names[position]
                )
                for position, table in enumerate(self.destination_tables)
            ]
        )

    def cancel_detection(self) -> bool:
        if self.isCanceled():
            clean_after_analysis(self)
            return True
        return False
