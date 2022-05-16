# -*- coding: utf-8 -*-
import os

from .UI.import_raster_ui import ImportRaster_UI
from ..utils import project, iface


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

