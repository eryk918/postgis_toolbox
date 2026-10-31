# -*- coding: utf-8 -*-
from typing import Optional

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialogButtonBox
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from qgis.gui import QgsProjectionSelectionDialog

from .. import ImportRaster
from ..utils.raster_utils import raster_extensions, max_raster_untiled_size
from ...utils import repair_dialog, os, QDialog, get_all_rasters_from_project, \
    plugin_name, get_active_db_info, get_schema_names, standardize_path, \
    NewThreadAlg, tr, remove_unsupported_chars, get_plugin_object, \
    read_setting, save_setting, read_bool_setting

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'import_raster_ui.ui'))

OVERVIEW_LEVELS = \
    ['2', '4', '8', '16', '32', '64', '128', '256', '512', '1024', '2048']
TILE_PRESETS = [64, 128, 256, 512, 1024, 2048]


class ImportRaster_UI(QDialog, FORM_CLASS):
    def __init__(self, importRaster, parent=None):
        super(ImportRaster_UI, self).__init__(parent)
        self.setupUi(self)
        self.importRaster = importRaster
        repair_dialog(self, 'import_raster_layers.svg')

    def setup_dialog(self) -> None:
        self.manage_rasters()
        con_status = \
            get_active_db_info(self.importRaster.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.button_box.button(QDialogButtonBox.Ok).setText(tr('Import'))
        self.button_box.accepted.connect(self.validate_fields)
        self.layer_file_widget.setDialogTitle(
            f"{plugin_name} - {tr('select a raster file: ')}")
        self.layer_file_widget.setFilter(
            ' '.join([f'*.{ext}' for ext in raster_extensions]))
        self.layer_file_widget.fileChanged.connect(self.select_raster_file)
        self.raster_layer_cbbx.currentTextChanged[str].connect(
            self.change_dest_raster_table_name)
        self.overview_combobox.addItems(OVERVIEW_LEVELS)
        self.overview_combobox.setCheckedItems(OVERVIEW_LEVELS)
        self.change_conn_btn.clicked.connect(self.change_db)
        self.tile_preset_cbbx.addItems(
            [f'{size} x {size}' for size in TILE_PRESETS])
        self.tile_preset_cbbx.addItem(tr('Custom'))
        self.tile_preset_cbbx.currentIndexChanged.connect(
            self.apply_tile_preset)
        self.restore_settings()

    def restore_settings(self) -> None:
        schema = read_setting('import_raster/schema', '')
        if schema and self.schema_cbbx.findText(schema) != -1:
            self.schema_cbbx.setCurrentText(schema)
        for name, checkbox in self.option_checkboxes().items():
            checkbox.setChecked(read_bool_setting(
                f'import_raster/{name}', checkbox.isChecked()))
        self.raster_tile_width_spinbox.setValue(int(read_setting(
            'import_raster/tile_width', self.raster_tile_width_spinbox.value())))
        self.raster_tile_height_spinbox.setValue(int(read_setting(
            'import_raster/tile_height',
            self.raster_tile_height_spinbox.value())))
        levels = read_setting('import_raster/overview_levels', None)
        if levels:
            self.overview_combobox.setCheckedItems(
                [level for level in levels if level in OVERVIEW_LEVELS])
        self.sync_tile_preset()

    def apply_tile_preset(self, index: int) -> None:
        custom = index >= len(TILE_PRESETS)
        self.raster_tile_width_spinbox.setEnabled(custom)
        self.raster_tile_height_spinbox.setEnabled(custom)
        if custom or index < 0:
            return
        size = TILE_PRESETS[index]
        self.raster_tile_width_spinbox.setValue(size)
        self.raster_tile_height_spinbox.setValue(size)

    def sync_tile_preset(self) -> None:
        width = self.raster_tile_width_spinbox.value()
        height = self.raster_tile_height_spinbox.value()
        index = TILE_PRESETS.index(width) \
            if width == height and width in TILE_PRESETS \
            else len(TILE_PRESETS)
        self.tile_preset_cbbx.blockSignals(True)
        self.tile_preset_cbbx.setCurrentIndex(index)
        self.tile_preset_cbbx.blockSignals(False)
        self.apply_tile_preset(index)

    def save_settings(self) -> None:
        save_setting('import_raster/schema', self.schema_cbbx.currentText())
        for name, checkbox in self.option_checkboxes().items():
            save_setting(f'import_raster/{name}', checkbox.isChecked())
        save_setting('import_raster/tile_width',
                     self.raster_tile_width_spinbox.value())
        save_setting('import_raster/tile_height',
                     self.raster_tile_height_spinbox.value())
        save_setting('import_raster/overview_levels',
                     self.overview_combobox.checkedItems())

    def option_checkboxes(self) -> dict:
        return {
            'tiling': self.tiling_groupbox,
            'pyramids': self.pyramids_chkbox,
            'overwrite': self.overwrite_chkbox,
            'compress': self.compress_chkbox,
            'add_project': self.add_project_chkbox,
        }

    def change_dest_raster_table_name(self, raster_name: str) -> None:
        new_raster_name = raster_name
        if "     ||  " in new_raster_name:
            new_raster_name = new_raster_name.split('     ||  ')[0]
        self.tablename_lineedit.setText(new_raster_name.lower())
        self.get_raster_filesize(raster_name)

    def run_dialog(self, check: bool = True) -> None:
        self.show()
        if self.raster_dict:
            raster_name = list(self.raster_dict.keys())[0].lower()
            if "     ||  " in raster_name:
                raster_name = raster_name.split('     ||  ')[0]
            self.tablename_lineedit.setText(raster_name)
        if check:
            self.get_raster_filesize(self.raster_layer_cbbx.currentText())
        self.exec()

    def manage_rasters(self) -> None:
        self.raster_layer_cbbx.clear()
        self.raster_dict = get_all_rasters_from_project()
        if not self.raster_dict:
            return
        self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))

    def get_schemas(self) -> None:
        self.schema_cbbx.clear()
        self.schema_cbbx.addItems(get_schema_names(self.importRaster.db))

    def set_object_visibility(self, visible: bool = True) -> None:
        self.destination_groupbox.setEnabled(visible)
        self.additional_params_groupbox.setEnabled(visible)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(visible)

    def get_raster_filesize(self, value: str = None) -> None:
        if not value:
            return
        size = os.path.getsize(self.raster_dict[value])
        if size >= max_raster_untiled_size:
            self.bar.pushInfo(
                plugin_name,
                tr('The file size exceeds the maximum size allowed for an '
                   'untiled raster.\nThe tiling option has been forced.'))
            self.tiling_groupbox.setChecked(True)
            self.tiling_groupbox.clicked.connect(
                lambda: self.tiling_groupbox.setChecked(True))
        else:
            try:
                self.tiling_groupbox.disconnect()
            except TypeError:
                pass

    def change_db(self):
        get_plugin_object().run_db_config()
        self.importRaster.db = get_plugin_object().db
        self.close()
        self.manage_rasters()
        con_status = \
            get_active_db_info(self.importRaster.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)
        self.run_dialog(False)

    def select_raster_file(self, filepath: str) -> None:
        filepath = standardize_path(filepath)
        if filepath and filepath != '.':
            filename, ext = os.path.splitext(os.path.basename(filepath))
            self.raster_dict[filename] = filepath
            self.raster_layer_cbbx.clear()
            self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))
            self.raster_layer_cbbx.setCurrentIndex(
                list(self.raster_dict.keys()).index(filename))
            self.tablename_lineedit.setText(filename.lower())

    def get_raster_srid(self, input_file: str) -> Optional[int]:
        srid = QgsRasterLayer(input_file, 'base').crs().postgisSrid()
        if srid:
            return srid
        selection_dialog = QgsProjectionSelectionDialog(self)
        selection_dialog.setCrs(QgsCoordinateReferenceSystem())
        if selection_dialog.exec() and selection_dialog.crs().isValid():
            return selection_dialog.crs().postgisSrid()
        return None

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
            input_file = standardize_path(
                self.raster_dict[self.raster_layer_cbbx.currentText()])
            srid = self.get_raster_srid(input_file)
            if srid is None:
                return
            self.save_settings()
            self.accept()
            self.info_dict = {
                'plugin_name': plugin_name,
                'alg_name': tr('Import raster into PostGIS database')
            }
            self.param_dict = {
                'input_file': input_file,
                'srid': srid,
                'layer_name': self.raster_layer_cbbx.currentText(),
                'tile_width': self.raster_tile_width_spinbox.value(),
                'tile_height': self.raster_tile_height_spinbox.value(),
                'destination_schema': self.schema_cbbx.currentText(),
                'destination_table': remove_unsupported_chars(
                    self.tablename_lineedit.text()),
                'q_overwrite': self.overwrite_chkbox.isChecked(),
                'q_pyramids': self.pyramids_chkbox.isChecked(),
                'q_make_tiles': self.tiling_groupbox.isChecked(),
                'q_compress': self.compress_chkbox.isChecked(),
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
            self.bar.pushWarning(plugin_name, tr('Setup correct parameters!'))
