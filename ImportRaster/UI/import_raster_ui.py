# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QMessageBox
from qgis.PyQt import uic

from ...utils import repair_comboboxes, main_plugin_icon, os, \
    QDialog, get_all_rasters_from_project, plugin_name, get_active_db_info, \
    get_schema_name_list

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'import_raster_ui.ui'))


class ImportRaster_UI(QDialog, FORM_CLASS):
    def __init__(self, importRaster, parent=None):
        super(ImportRaster_UI, self).__init__(parent)
        self.setupUi(self)
        self.importRaster = importRaster
        repair_comboboxes(self)
        self.setWindowIcon(main_plugin_icon)

    def setup_dialog(self) -> None:
        self.manage_rasters()
        con_status = \
            get_active_db_info(self.importRaster.db, self.active_db_label)
        if con_status:
            self.get_schemas()
        self.set_object_visibility(con_status)

    def run_dialog(self) -> None:
        self.show()
        if not self.raster_dict:
            self.close()
            QMessageBox.critical(
                self.dlg, plugin_name,
                'No raster layers were detected in the project.',
                QMessageBox.Ok)
        self.exec_()

    def manage_rasters(self) -> None:
        self.raster_dict = get_all_rasters_from_project()
        if not self.raster_dict:
            return
        self.raster_layer_cbbx.addItems(list(self.raster_dict.keys()))

    def get_schemas(self) -> None:
        schemas_list, _ = get_schema_name_list(
            self.importRaster.db, change_db=False)
        if schemas_list:
            self.schema_cbbx.addItems(schemas_list)

    def set_object_visibility(self, visible: bool = True) -> None:
        self.destination_frame.setEnabled(visible)
        self.additional_params_groupbox.setEnabled(visible)
        self.import_btn.setEnabled(visible)

