# -*- coding: utf-8 -*-

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog

from .. import ImportRaster
from ..utils.raster_utils import raster_extensions, max_raster_untiled_size
from ...utils import repair_dialog, main_plugin_icon, os, \
    QDialog, get_all_rasters_from_project, plugin_name, get_active_db_info, \
    get_schema_name_list, standarize_path, NewThreadAlg, tr, \
    remove_unsupported_chars, get_main_plugin_class

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'import_raster_ui.ui'))

OVERVIEW_LEVELS = \
    ['2', '4', '8', '16', '32', '64', '128', '256', '512', '1024', '2048']


class ImportRaster_UI(QDialog, FORM_CLASS):
    def __init__(self, importRaster, parent=None):
        super(ImportRaster_UI, self).__init__(parent)
        self.setupUi(self)
        self.importRaster = importRaster
        repair_dialog(self)
        self.setWindowIcon(main_plugin_icon)

    def setup_dialog(self) -> None:
        self.manage_rasters()
        con_status = \
            get_active_db_info(self.importRaster.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.import_btn.clicked.connect(self.validate_fields)
        self.browse_layer_btn.clicked.connect(self.select_raster_file)
        self.raster_layer_cbbx.currentTextChanged[str].connect(
            lambda value: self.tablename_lineedit.setText(value.lower()))
        self.raster_layer_cbbx.currentTextChanged[str].connect(
            self.get_raster_filesize)
        self.overview_combobox.addItems(OVERVIEW_LEVELS)
        self.overview_combobox.setCheckedItems(OVERVIEW_LEVELS)
        self.change_conn_btn.clicked.connect(self.change_db)

    def run_dialog(self, check: bool = True) -> None:
        self.show()
        if not self.raster_dict:
            self.close()
            QMessageBox.critical(
                self, plugin_name,
                'No raster layers were detected in the project.',
                QMessageBox.Ok)
        self.tablename_lineedit.setText(
            list(self.raster_dict.keys())[0].lower())
        if check:
            self.get_raster_filesize(self.raster_layer_cbbx.currentText())
        self.exec_()

    def manage_rasters(self) -> None:
        self.raster_layer_cbbx.clear()
        self.raster_dict = get_all_rasters_from_project()
        if not self.raster_dict:
            return
        self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))

    def get_schemas(self) -> None:
        self.schema_cbbx.clear()
        schemas_list, _ = get_schema_name_list(
            self.importRaster.db, change_db=False)
        if schemas_list:
            self.schema_cbbx.addItems(schemas_list)

    def set_object_visibility(self, visible: bool = True) -> None:
        self.destination_frame.setEnabled(visible)
        self.additional_params_groupbox.setEnabled(visible)
        self.import_btn.setEnabled(visible)

    def get_raster_filesize(self, value: str) -> None:
        if not value:
            return
        size = os.path.getsize(self.raster_dict[value])
        if size >= max_raster_untiled_size:
            QMessageBox.warning(
                self,
                tr('Warning'),
                tr('The file size exceeds the maximum size allowed for an '
                   'untiled raster.\nThe tiling option has been forced.'),
                QMessageBox.Ok)
            self.tiling_groupbox.clicked.connect(
                lambda: self.tiling_groupbox.setChecked(True))
        else:
            try:
                self.tiling_groupbox.disconnect()
            except TypeError:
                pass

    def change_db(self):
        get_main_plugin_class().run_db_config()
        self.importRaster.db = get_main_plugin_class().db
        self.close()
        self.manage_rasters()
        con_status = \
            get_active_db_info(self.importRaster.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.run_dialog(False)

    def select_raster_file(self) -> None:
        filepath, __ = QFileDialog.getOpenFileName(
            self, tr("Select a raster file:"),
            "", ' '.join([f'*.{ext}' for ext in raster_extensions]))
        filepath = standarize_path(filepath)
        if filepath and filepath != '.':
            filename, ext = os.path.splitext(os.path.basename(filepath))
            self.raster_dict[filename] = filepath
            self.raster_layer_cbbx.clear()
            self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))
            self.raster_layer_cbbx.setCurrentIndex(
                list(self.raster_dict.keys()).index(filename))
            self.tablename_lineedit.setText(filename.lower())

    def validate_fields(self) -> None:
        if (self.raster_layer_cbbx.currentText() and
            self.tablename_lineedit.text() and
            self.schema_cbbx.currentText() and
            not self.pyramids_chkbox.isChecked()) or (
                self.raster_layer_cbbx.currentText() and
                self.tablename_lineedit.text() and
                self.schema_cbbx.currentText() and
                self.pyramids_chkbox.isChecked() and
                self.overview_combobox.checkedItems()):
            self.accept()
            self.info_dict = {
                'plugin_name': plugin_name,
                'alg_name': tr('Import raster into PostGIS database')
            }
            self.param_dict = {
                'input_file': standarize_path(
                    self.raster_dict[self.raster_layer_cbbx.currentText()]),
                'layer_name': self.raster_layer_cbbx.currentText(),
                'tile_width': self.raster_tile_width_spinbox.value(),
                'tile_height': self.raster_tile_height_spinbox.value(),
                'destination_schema': self.schema_cbbx.currentText(),
                'destination_table': remove_unsupported_chars(
                    self.tablename_lineedit.text()),
                'q_pyramids': self.pyramids_chkbox.isChecked(),
                'q_make_tiles': self.tiling_groupbox.isChecked(),
                'q_add_to_project': self.add_project_chkbox.isChecked(),
                'checked_overview':
                    [int(ov) for ov in self.overview_combobox.checkedItems()]
            }
            thread = NewThreadAlg(
                self.info_dict,
                ImportRaster.RasterImporter(
                    f"{self.info_dict['plugin_name']}: {self.info_dict['alg_name']}",
                    self.importRaster.main, self.param_dict),
                True)
            thread.start()
        else:
            QMessageBox.warning(
                self,
                tr('Warning'),
                tr('Setup correct parameters!'),
                QMessageBox.Ok)
