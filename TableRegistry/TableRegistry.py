# -*- coding: utf-8 -*-
from functools import partial


from .UI.table_registry_dialog import TableRegistryDialog
from .utils.registry_utils import TableInfo, load_tables, details_rows, \
    rename_table, drop_table, table_names_in_schema
from ..DBManager.UI.db_manager_add import DBManagerAdd_UI
from ..utils import iface, tr, plugin_name, get_active_db_info, ask_question, \
    show_error, show_info, check_connection, create_postgis_vector_layer, \
    create_postgis_raster_layer, add_vectors_to_project, \
    add_rasters_to_project, VECTORS_LAYERS_GROUP, RASTERS_LAYERS_GROUP, Qt


class TableRegistry:
    def __init__(self, parent) -> None:
        self.main = parent
        self.dlg = None
        self.tables = []

    def run(self) -> None:
        if not check_connection(self.main.db):
            show_error(
                iface.mainWindow(),
                tr('There is no connection to the PostGIS database!'))
            return
        if self.dlg is None:
            self.dlg = TableRegistryDialog(self, iface.mainWindow())
        self.refresh()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.setWindowState(self.dlg.windowState() & ~Qt.WindowMinimized)
        self.dlg.activateWindow()

    def sync_active_db(self) -> None:
        if self.dlg is None or not self.dlg.isVisible():
            return
        if self.main.db is None:
            self.dlg.close()
        else:
            self.refresh()

    def refresh(self) -> None:
        get_active_db_info(self.main.db, self.dlg.active_db_label)
        self.tables = load_tables(self.main.db) if self.main.db else []
        self.dlg.fill_tables(self.tables)

    def show_details(self, info: TableInfo) -> None:
        if not self.main.db:
            return
        self.dlg.fill_details(details_rows(self.main.db, info))

    def add_layer(self) -> None:
        info = self.dlg.selected_table()
        if info is None or not self.main.db:
            return
        if info.is_raster():
            layers = [create_postgis_raster_layer(
                self.main.db, info.schema, info.name, info.name,
                info.raster_column)]
        elif info.is_vector():
            layers = [
                create_postgis_vector_layer(
                    self.main.db, info.schema, info.name, column,
                    info.name if len(info.geometry_columns) == 1
                    else f'{info.name} ({column})')
                for column, _, _, _ in info.geometry_columns]
        else:
            layers = [create_postgis_vector_layer(
                self.main.db, info.schema, info.name, '', info.name)]
        invalid = [layer.name() for layer in layers if not layer.isValid()]
        if invalid:
            show_error(
                self.dlg,
                tr('Failed to load the layer "{0}".').format(invalid[0]))
            return
        if info.is_raster():
            add_rasters_to_project(
                RASTERS_LAYERS_GROUP, layers, postgis_raster=True)
        else:
            add_vectors_to_project(VECTORS_LAYERS_GROUP, layers)

    def rename_table(self) -> None:
        info = self.dlg.selected_table()
        if info is None or not check_connection(self.main.db):
            return
        dialog = DBManagerAdd_UI(self, self.dlg)
        dialog.setup_dialog(
            tr('Enter a new name for "{0}"').format(info.name),
            tr('Table name...'))
        dialog.run_dialog(
            partial(self.rename_to, info),
            table_names_in_schema(self.tables, info.schema))

    def rename_to(self, info: TableInfo, new_name: str) -> None:
        if rename_table(self.main.db, info, new_name):
            show_info(
                self.dlg,
                tr('Successfully renamed "{0}" to "{1}".').format(
                    info.name, new_name))
        else:
            show_error(
                self.dlg,
                tr('An error occurred while renaming the table!'))
        self.refresh()

    def delete_table(self) -> None:
        info = self.dlg.selected_table()
        if info is None or not check_connection(self.main.db):
            return
        names = [info.qualified_name()] + [
            f'{schema}.{table}' for schema, table, _ in info.overviews]
        response = ask_question(
            self.dlg,
            tr('Do you want to drop {0}?\nThis cannot be undone.').format(
               ', '.join(names)))
        if not response:
            return
        if drop_table(self.main.db, info):
            show_info(
                self.dlg,
                tr('Successfully dropped "{0}".').format(info.name))
        else:
            show_error(
                self.dlg,
                tr('An error occurred while dropping the table!'))
        self.refresh()

    def close(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
