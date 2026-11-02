# -*- coding: utf-8 -*-
from typing import Dict, List, Optional

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialogButtonBox
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from qgis.gui import QgsProjectionSelectionDialog, QgsFileWidget

from .. import ImportRaster
from ..utils.raster_utils import raster_extensions, max_raster_untiled_size
from ...utils import repair_dialog, os, QDialog, \
    get_all_rasters_from_project, \
    plugin_name, get_active_db_info, get_schema_names, standardize_path, \
    NewThreadAlg, tr, remove_unsupported_chars, get_plugin_object, \
    read_setting, save_setting, read_bool_setting

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'import_raster_ui.ui'))

OVERVIEW_LEVELS = \
    ['2', '4', '8', '16', '32', '64', '128', '256', '512', '1024', '2048']
TILE_PRESETS = [64, 128, 256, 512, 1024, 2048]
LAYER_ID_SEPARATOR = '     ||  '


def table_name_for(layer_key: str) -> str:
    name = layer_key.split(LAYER_ID_SEPARATOR)[0]
    return remove_unsupported_chars(name.lower())


class ImportRaster_UI(QDialog, FORM_CLASS):
    def __init__(self, importRaster, parent=None):
        super(ImportRaster_UI, self).__init__(parent)
        self.setupUi(self)
        self.importRaster = importRaster
        self.raster_dict = {}
        self.tiling_forced = False
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
        self.layer_file_widget.setStorageMode(QgsFileWidget.GetMultipleFiles)
        self.layer_file_widget.setDialogTitle(
            f"{plugin_name} - {tr('Select raster files')}")
        self.layer_file_widget.setFilter(
            ' '.join([f'*.{ext}' for ext in raster_extensions]))
        self.layer_file_widget.fileChanged.connect(self.select_raster_files)
        self.raster_layer_cbbx.checkedItemsChanged.connect(
            self.selection_changed)
        self.overview_combobox.addItems(OVERVIEW_LEVELS)
        self.overview_combobox.setCheckedItems(OVERVIEW_LEVELS)
        self.change_conn_btn.clicked.connect(self.change_db)
        self.tiling_groupbox.clicked.connect(self.keep_forced_tiling)
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
            'import_raster/tile_width',
            self.raster_tile_width_spinbox.value())))
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

    def selected_keys(self) -> List[str]:
        return [key for key in self.raster_layer_cbbx.checkedItems()
                if key in self.raster_dict]

    def selection_changed(self) -> None:
        keys = self.selected_keys()
        self.tablename_lineedit.setEnabled(len(keys) <= 1)
        self.tablename_lineedit.setText(
            ', '.join(table_name_for(key) for key in keys))
        self.check_file_sizes(keys)

    def check_file_sizes(self, keys: List[str]) -> None:
        large = [key for key in keys
                 if os.path.exists(self.raster_dict[key]) and
                 os.path.getsize(self.raster_dict[key]) >=
                 max_raster_untiled_size]
        self.tiling_forced = bool(large)
        if self.tiling_forced:
            self.tiling_groupbox.setChecked(True)
            self.bar.pushInfo(
                plugin_name,
                tr('The file size exceeds the maximum size allowed for an '
                   'untiled raster.\nThe tiling option has been forced.'))

    def keep_forced_tiling(self) -> None:
        if self.tiling_forced:
            self.tiling_groupbox.setChecked(True)

    def run_dialog(self) -> None:
        self.show()
        self.exec()

    def manage_rasters(self) -> None:
        self.raster_layer_cbbx.clear()
        self.raster_dict = get_all_rasters_from_project()
        self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))
        keys = list(self.raster_dict.keys())
        if keys:
            self.raster_layer_cbbx.setCheckedItems(keys[:1])
        self.selection_changed()

    def get_schemas(self) -> None:
        self.schema_cbbx.clear()
        self.schema_cbbx.addItems(get_schema_names(self.importRaster.db))

    def set_object_visibility(self, visible: bool = True) -> None:
        self.destination_groupbox.setEnabled(visible)
        self.additional_params_groupbox.setEnabled(visible)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(visible)

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
        self.run_dialog()

    def select_raster_files(self, value: str) -> None:
        added = []
        for filepath in QgsFileWidget.splitFilePaths(value):
            filepath = standardize_path(filepath)
            if not filepath or filepath == '.' or \
                    not os.path.exists(filepath):
                continue
            filename = os.path.splitext(os.path.basename(filepath))[0]
            self.raster_dict[filename] = filepath
            added.append(filename)
        if not added:
            return
        checked = [key for key in self.raster_layer_cbbx.checkedItems()
                   if key not in added]
        self.raster_layer_cbbx.clear()
        self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))
        self.raster_layer_cbbx.setCheckedItems(checked + added)
        self.selection_changed()

    def ask_srid(self) -> Optional[int]:
        selection_dialog = QgsProjectionSelectionDialog(self)
        selection_dialog.setCrs(QgsCoordinateReferenceSystem())
        if selection_dialog.exec() and selection_dialog.crs().isValid():
            return selection_dialog.crs().postgisSrid() or None
        return None

    def build_jobs(self, keys: List[str]) -> Optional[List[Dict]]:
        jobs = []
        fallback_srid = None
        for key in keys:
            input_file = standardize_path(self.raster_dict[key])
            srid = QgsRasterLayer(input_file, 'base').crs().postgisSrid()
            if not srid:
                if fallback_srid is None:
                    fallback_srid = self.ask_srid()
                    if fallback_srid is None:
                        return None
                srid = fallback_srid
            table = remove_unsupported_chars(self.tablename_lineedit.text()) \
                if len(keys) == 1 else table_name_for(key)
            jobs.append({
                'input_file': input_file,
                'srid': srid,
                'layer_name': key.split(LAYER_ID_SEPARATOR)[0],
                'destination_table': table,
            })
        return jobs

    def validate_fields(self) -> None:
        keys = self.selected_keys()
        valid = keys and self.schema_cbbx.currentText() and \
            self.tablename_lineedit.text() and (
                not self.pyramids_chkbox.isChecked() or
                self.overview_combobox.checkedItems())
        if not valid:
            self.bar.pushWarning(
                plugin_name, tr('Fill in the required fields.'))
            return
        jobs = self.build_jobs(keys)
        if not jobs:
            return
        self.save_settings()
        self.accept()
        info_dict = {
            'plugin_name': plugin_name,
            'alg_name': tr('Import raster into PostGIS database')
            if len(jobs) == 1 else
            tr('Import of {0} rasters into PostGIS database').format(
                len(jobs))
        }
        param_dict = {
            'jobs': jobs,
            'tile_width': self.raster_tile_width_spinbox.value(),
            'tile_height': self.raster_tile_height_spinbox.value(),
            'destination_schema': self.schema_cbbx.currentText(),
            'q_overwrite': self.overwrite_chkbox.isChecked(),
            'q_pyramids': self.pyramids_chkbox.isChecked(),
            'q_make_tiles': self.tiling_groupbox.isChecked(),
            'q_compress': self.compress_chkbox.isChecked(),
            'q_add_to_project': self.add_project_chkbox.isChecked(),
            'checked_overview':
                [int(ov) for ov in self.overview_combobox.checkedItems()]
        }
        thread = NewThreadAlg(
            info_dict,
            ImportRaster.RasterImporter(
                f"{info_dict['plugin_name']}: {info_dict['alg_name']}",
                self.importRaster.main, param_dict),
            True)
        thread.start()
