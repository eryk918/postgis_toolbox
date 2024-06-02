# -*- coding: utf-8 -*-
from typing import Dict

from osgeo import ogr
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog
from qgis.core import QgsVectorLayer

from .. import ImportVector
from ..utils.vector_utils import vector_extensions, simple_vector_extensions
from ...utils import repair_dialog, os, \
    QDialog, get_all_vectors_from_project, plugin_name, get_active_db_info, \
    get_schema_name_list, standardize_path, NewThreadAlg, tr, \
    remove_unsupported_chars, get_plugin_object, project

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'import_vector_ui.ui'))


class ImportVector_UI(QDialog, FORM_CLASS):
    def __init__(self, import_vector, parent=None):
        super(ImportVector_UI, self).__init__(parent)
        self.setupUi(self)
        self.import_vector = import_vector
        repair_dialog(self, 'import_vector_layer.png')

    def setup_dialog(self) -> None:
        self.manage_vectors()
        con_status = \
            get_active_db_info(self.import_vector.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.import_btn.clicked.connect(self.validate_fields)
        self.browse_layer_btn.clicked.connect(self.select_vector_file)
        self.vector_layer_cbbx.checkedItemsChanged.connect(
            self.add_layer_table_names)
        self.change_conn_btn.clicked.connect(self.change_db)

    def run_dialog(self) -> None:
        self.show()
        self.exec_()

    def manage_vectors(self) -> None:
        self.vector_layer_cbbx.clear()
        self.vector_dict = get_all_vectors_from_project()
        if not self.vector_dict:
            return
        self.vector_layer_cbbx.addItems(list(self.vector_dict.keys()))

    def get_schemas(self) -> None:
        self.schema_cbbx.clear()
        schemas_list, _ = get_schema_name_list(
            self.import_vector.db, change_db=False)
        if schemas_list:
            self.schema_cbbx.addItems(schemas_list)

    def set_object_visibility(self, visible: bool = True) -> None:
        self.destination_frame.setEnabled(visible)
        self.additional_params_groupbox.setEnabled(visible)
        self.import_btn.setEnabled(visible)

    def add_layer_table_names(self) -> None:
        self.tablename_lineedit.setEnabled(True)
        self.tablename_lineedit.setText(
            ', '.join(self.vector_layer_cbbx.checkedItems()).lower())
        self.tablename_lineedit.setEnabled(
            not len(self.vector_layer_cbbx.checkedItems()) > 1)

    def change_db(self):
        get_plugin_object().run_db_config()
        self.import_vector.db = get_plugin_object().db
        self.close()
        self.manage_vectors()
        con_status = \
            get_active_db_info(self.import_vector.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.run_dialog()

    def select_vector_file(self) -> None:
        filepath, __ = QFileDialog.getOpenFileName(
            self, f"PostGIS Toolbox - {tr('select a vector file: ')}",
            "", ' '.join([f'*.{ext}' for ext in vector_extensions]))
        filepath = standardize_path(filepath)
        if filepath and filepath != '.' and os.path.exists(filepath):
            filename, ext = os.path.splitext(os.path.basename(filepath))
            filenames = []
            if ext.lower() not in simple_vector_extensions:
                for filename, filepath in self.get_layers_from_container(filepath).items():
                    tmp_layer = QgsVectorLayer(filepath, filename, "ogr")
                    if not tmp_layer.isValid():
                        QMessageBox.warning(
                            self,
                            tr('Error'),
                            tr('The selected file is not a vector format file!'),
                            QMessageBox.Ok)
                        return
                    self.vector_dict[filename] = (
                        filepath, int(tmp_layer.wkbType()))
                    filenames.append(filename)
            else:
                tmp_layer = QgsVectorLayer(filepath, filename, "ogr")
                if not tmp_layer.isValid():
                    QMessageBox.warning(
                        self,
                        tr('Error'),
                        tr('The selected file is not a vector format file!'),
                        QMessageBox.Ok)
                    return
                self.vector_dict[filename] = (filepath, int(tmp_layer.wkbType()))
                filenames = [filename]
            self.vector_layer_cbbx.clear()
            self.vector_layer_cbbx.addItems(list(self.vector_dict.keys()))
            self.vector_layer_cbbx.setCheckedItems(filenames)

    def get_layers_from_container(self, input_file: str) -> Dict[str, str]:
        return {layer.GetName(): f'{input_file}|layername={layer.GetName()}'
                for layer in ogr.Open(input_file)}

    def validate_fields(self) -> None:
        if self.vector_layer_cbbx.checkedItems() and \
                self.tablename_lineedit.text() and \
                self.schema_cbbx.currentText():
            self.accept()
            self.info_dict = {
                'plugin_name': plugin_name,
                'alg_name': tr('Import vector into PostGIS database')
            }
            self.param_dict = {
                'input_files': [
                    standardize_path(self.vector_dict[file][0])
                    for file in self.vector_layer_cbbx.checkedItems()
                ],
                'layer_names': [
                    file
                    for file in self.vector_layer_cbbx.checkedItems()
                ],
                'layer_types': [
                    self.vector_dict[file][1]
                    for file in self.vector_layer_cbbx.checkedItems()
                ],
                'destination_schema': self.schema_cbbx.currentText(),
                'destination_tables': [
                    remove_unsupported_chars(table_name)
                    for table_name in
                    self.tablename_lineedit.text().split(', ')
                ],
                'q_add_to_project': self.add_project_chkbox.isChecked(),
                'q_create_index': self.create_index_chkbox.isChecked(),
                'q_lower_case': self.lower_case_chkbox.isChecked(),
                'q_drop_length': self.drop_length_chkbox.isChecked(),
                'q_overwrite': self.overwrite_chkbox.isChecked(),
                'q_force_singlepart': self.force_singlepart_chkbox.isChecked()
            }
            thread = NewThreadAlg(
                self.info_dict,
                ImportVector.VectorImporter(
                    f"{self.info_dict['plugin_name']}: {self.info_dict['alg_name']}",
                    self.import_vector.main, self.param_dict),
                True)
            thread.start()
        else:
            QMessageBox.warning(
                self,
                tr('Warning'),
                tr('Setup correct parameters!'),
                QMessageBox.Ok)
