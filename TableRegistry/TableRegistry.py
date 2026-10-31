# -*- coding: utf-8 -*-
from functools import partial
from typing import Any, Callable, List, Optional, Tuple

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsCoordinateReferenceSystem, QgsMapLayer, \
    QgsProject, QgsApplication, QgsTask
from qgis.gui import QgsProjectionSelectionDialog

from .UI.privileges_dialog import PrivilegesDialog
from .UI.table_registry_dialog import TableRegistryDialog
from .utils import admin_utils
from .utils.export_utils import export_vector, export_raster
from .utils.task_utils import RegistryTask
from .utils.registry_utils import TableInfo, load_tables, details_rows, \
    rename_table, drop_table, table_names_in_schema
from ..CustomQueryBuilder.UI.new_object_dialog import NewObjectDialog
from ..DBManager.UI.db_manager_add import DBManagerAdd_UI
from ..utils import iface, tr, get_active_db_info, \
    ask_question, show_error, show_info, check_connection, \
    create_postgis_vector_layer, create_postgis_raster_layer, \
    add_vectors_to_project, add_rasters_to_project, VECTORS_LAYERS_GROUP, \
    RASTERS_LAYERS_GROUP, get_schema_names, connection_uri, Qt, make_query


class TableRegistry:
    def __init__(self, parent) -> None:
        self.main = parent
        self.dlg = None
        self.tables = []
        self.privileges_dialog = None
        self.task = None
        self.progress_sql = None
        self.progress_timer = QTimer()
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self.poll_progress)

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

    def selected(self) -> Optional[TableInfo]:
        info = self.dlg.selected_table()
        if info is None or not check_connection(self.main.db):
            return None
        return info

    def show_details(self, info: TableInfo) -> None:
        if not self.main.db:
            return
        details = details_rows(self.main.db, info)
        size = admin_utils.table_size(self.main.db, info)
        if size:
            details['size'] = [('', size)]
        details['maintenance'] = admin_utils.table_maintenance(
            self.main.db, info)
        owner = admin_utils.table_owner(self.main.db, info)
        if owner:
            details['owner'] = [('', owner)]
        details['privileges'] = admin_utils.table_privileges(
            self.main.db, info)
        self.dlg.fill_details(details)

    def layer_uris(self, info: TableInfo) -> List[Tuple[str, str, str]]:
        if info.is_raster():
            uri = connection_uri(self.main.db)
            uri.setSchema(info.schema)
            uri.setTable(info.name)
            uri.setGeometryColumn(info.raster_column)
            return [('postgresraster', uri.uri(False), info.name)]
        columns = [column for column, _, _, _ in info.geometry_columns] \
            or [None]
        uris = []
        for column in columns:
            uri = connection_uri(self.main.db)
            uri.setDataSource(info.schema, info.name, column)
            name = info.name if len(columns) == 1 \
                else f'{info.name} ({column})'
            uris.append(('postgres', uri.uri(False), name))
        return uris

    def build_layers(self, info: TableInfo) -> List[QgsMapLayer]:
        if info.is_raster():
            return [create_postgis_raster_layer(
                self.main.db, info.schema, info.name, info.name,
                info.raster_column)]
        if info.is_vector():
            return [
                create_postgis_vector_layer(
                    self.main.db, info.schema, info.name, column,
                    info.name if len(info.geometry_columns) == 1
                    else f'{info.name} ({column})')
                for column, _, _, _ in info.geometry_columns]
        return [create_postgis_vector_layer(
            self.main.db, info.schema, info.name, '', info.name)]

    def valid_layers(self, info: TableInfo) -> List[QgsMapLayer]:
        layers = self.build_layers(info)
        invalid = [layer.name() for layer in layers if not layer.isValid()]
        if invalid:
            show_error(
                self.dlg,
                tr('Failed to load the layer "{0}".').format(invalid[0]))
            return []
        return layers

    def add_layer(self) -> None:
        info = self.selected()
        if info is None:
            return
        layers = self.valid_layers(info)
        if not layers:
            return
        if info.is_raster():
            add_rasters_to_project(
                RASTERS_LAYERS_GROUP, layers, postgis_raster=True)
        else:
            add_vectors_to_project(VECTORS_LAYERS_GROUP, layers)

    def export_table(self) -> None:
        info = self.selected()
        if info is None:
            return
        layers = self.valid_layers(info)
        if not layers:
            return
        exporter = export_raster if info.is_raster() else export_vector
        success, message, new_layer = exporter(layers[0], self.dlg)
        if success is None:
            return
        if not success:
            show_error(self.dlg,
                       tr('Export failed: {0}').format(message))
            return
        if new_layer is not None and new_layer.isValid():
            QgsProject.instance().addMapLayer(new_layer)
        show_info(self.dlg, tr('Exported "{0}" to {1}.').format(
            info.name, message))

    def rename_table(self) -> None:
        info = self.selected()
        if info is None:
            return
        dialog = DBManagerAdd_UI(self, self.dlg)
        dialog.setup_dialog(
            tr('Enter a new name for "{0}"').format(info.name),
            tr('Table name...'))
        dialog.run_dialog(
            partial(self.rename_to, info),
            table_names_in_schema(self.tables, info.schema))

    def rename_to(self, info: TableInfo, new_name: str) -> None:
        self.report(
            rename_table(self.main.db, info, new_name),
            tr('Successfully renamed "{0}" to "{1}".').format(
                info.name, new_name),
            tr('An error occurred while renaming the table!'))

    def delete_table(self) -> None:
        info = self.selected()
        if info is None:
            return
        names = [info.qualified_name()] + [
            f'{schema}.{table}' for schema, table, _ in info.overviews]
        if not ask_question(
                self.dlg,
                tr('Do you want to drop {0}?\nThis cannot be undone.').format(
                    ', '.join(names))):
            return
        self.report(
            drop_table(self.main.db, info),
            tr('Successfully dropped "{0}".').format(info.name),
            tr('An error occurred while dropping the table!'))

    def report(self, success: bool, done: str, failed: str) -> None:
        if success:
            show_info(self.dlg, done)
        else:
            show_error(self.dlg, failed)
        self.refresh()

    def run_task(self, description: str, function: Callable,
                 on_finished: Callable[[Any], None],
                 progress_sql: Optional[str] = None) -> None:
        if self.task is not None or not self.main.db:
            return
        task = RegistryTask(description, self.main.db.uri(), function)
        self.task = task
        self.progress_sql = progress_sql
        self.dlg.set_busy(True, description)
        task.taskCompleted.connect(
            partial(self.task_finished, task, on_finished))
        task.taskTerminated.connect(
            partial(self.task_finished, task, on_finished))
        if progress_sql:
            self.progress_timer.start()
        QgsApplication.taskManager().addTask(task)

    def task_finished(self, task: RegistryTask,
                      on_finished: Callable[[Any], None]) -> None:
        self.progress_timer.stop()
        self.task = None
        self.dlg.set_busy(False)
        completed = task.status() == QgsTask.Complete
        on_finished(task.result if completed else None)

    def poll_progress(self) -> None:
        if self.task is None or not self.progress_sql or not self.main.db:
            self.progress_timer.stop()
            return
        rows = make_query(self.main.db, self.progress_sql)
        if rows is None:
            self.progress_timer.stop()
            return
        if not rows or not rows[0][1]:
            return
        done, total = rows[0]
        percent = int(min(done, total) * 100 / total)
        self.dlg.set_progress(percent)
        self.task.setProgress(percent)

    def count_rows(self) -> None:
        info = self.selected()
        if info is None:
            return

        def finished(count: Optional[int]) -> None:
            if count is None:
                show_error(self.dlg,
                           tr('An error occurred while counting rows!'))
                return
            self.dlg.add_detail_section('exact_rows', [('', str(count))])

        self.run_task(
            tr('Counting rows of "{0}"').format(info.name),
            lambda connection: admin_utils.count_rows(connection, info),
            finished)

    def vacuum(self) -> None:
        info = self.selected()
        if info is None:
            return
        self.run_task(
            tr('Vacuum and analyze of "{0}"').format(info.name),
            lambda connection: admin_utils.vacuum_analyze(connection, info),
            partial(
                self.report_result,
                tr('Vacuum and analyze of "{0}" finished.').format(info.name),
                tr('Vacuum and analyze failed!')),
            admin_utils.vacuum_progress_sql(info))

    def report_result(self, done: str, failed: str, result: Any) -> None:
        self.report(bool(result), done, failed)

    def refresh_view(self) -> None:
        info = self.selected()
        if info is None:
            return
        self.run_task(
            tr('Refreshing "{0}"').format(info.name),
            lambda connection: admin_utils.refresh_materialized_view(
                connection, info),
            partial(
                self.report_result,
                tr('Materialized view "{0}" refreshed.').format(info.name),
                tr('Refreshing the materialized view failed!')))

    def add_primary_key(self) -> None:
        info = self.selected()
        if info is None:
            return
        if admin_utils.primary_key_columns(self.main.db, info):
            show_info(self.dlg,
                      tr('The table already has a primary key.'))
            return

        def finished(column: Optional[str]) -> None:
            self.report(
                column is not None,
                tr('Primary key column "{0}" added.').format(column),
                tr('Adding the primary key failed!'))

        self.run_task(
            tr('Adding primary key to "{0}"').format(info.name),
            lambda connection: admin_utils.add_primary_key(connection, info),
            finished)

    def create_spatial_index(self) -> None:
        info = self.selected()
        if info is None:
            return
        columns = [info.raster_column] if info.is_raster() \
            else [column for column, _, _, _ in info.geometry_columns]
        missing = [column for column in columns
                   if not admin_utils.has_spatial_index(
                       self.main.db, info, column)]
        if not missing:
            show_info(self.dlg,
                      tr('All spatial columns already have an index.'))
            return
        self.run_task(
            tr('Creating spatial index on "{0}"').format(info.name),
            lambda connection: all([
                admin_utils.create_spatial_index(connection, info, column)
                for column in missing]),
            partial(
                self.report_result,
                tr('Spatial index created on {0}.').format(
                    ', '.join(missing)),
                tr('Creating the spatial index failed!')),
            admin_utils.index_progress_sql(info))

    def ask_target(self, info: TableInfo, title: str,
                   default_name: str) -> Tuple[Optional[str], Optional[str]]:
        schemas = get_schema_names(self.main.db)
        if info.schema not in schemas:
            schemas.insert(0, info.schema)
        dialog = NewObjectDialog(title, tr('Table name'), schemas, self.dlg)
        dialog.schema_cbbx.setCurrentText(info.schema)
        dialog.name_lineedit.setText(default_name)
        if dialog.exec() != NewObjectDialog.Accepted:
            return None, None
        return dialog.schema_name(), dialog.object_name()

    def move_table(self) -> None:
        info = self.selected()
        if info is None:
            return
        schema, name = self.ask_target(
            info, tr('Move or rename "{0}"').format(info.name), info.name)
        if not schema or not name:
            return
        if schema == info.schema and name == info.name:
            return
        self.report(
            admin_utils.relocate_table(self.main.db, info, schema, name),
            tr('"{0}" is now {1}.{2}.').format(info.name, schema, name),
            tr('Moving the table failed!'))

    def copy_table(self) -> None:
        info = self.selected()
        if info is None:
            return
        schema, name = self.ask_target(
            info, tr('Copy "{0}" to schema').format(info.name),
            f'{info.name}_copy')
        if not schema or not name:
            return
        self.run_task(
            tr('Copying "{0}"').format(info.name),
            lambda connection: admin_utils.copy_table(
                connection, info, schema, name),
            partial(
                self.report_result,
                tr('Copied "{0}" to {1}.{2}.').format(info.name, schema, name),
                tr('Copying the table failed!')))

    def geometry_column(self, info: TableInfo) -> Optional[Tuple[str, int]]:
        if not info.geometry_columns:
            return None
        column, _, srid, _ = info.geometry_columns[0]
        return column, srid

    def check_geometries(self) -> None:
        info = self.selected()
        geometry = self.geometry_column(info) if info else None
        if geometry is None:
            return

        def finished(result: Optional[Tuple]) -> None:
            count, rows = result if result else (None, [])
            if count is None:
                show_error(self.dlg, tr('Geometry check failed!'))
                return
            if count == 0:
                self.dlg.add_detail_section(
                    'invalid', [('', tr('All geometries are valid.'))])
                return
            header = [(tr('Total'), str(count))]
            if count > len(rows):
                header.append((tr('Shown'), str(len(rows))))
            self.dlg.add_detail_section('invalid', header + rows)

        self.run_task(
            tr('Checking geometries of "{0}"').format(info.name),
            lambda connection: admin_utils.invalid_geometries(
                connection, info, geometry[0]),
            finished)

    def update_srid(self) -> None:
        info = self.selected()
        geometry = self.geometry_column(info) if info else None
        if geometry is None:
            return
        dialog = QgsProjectionSelectionDialog(self.dlg)
        dialog.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(geometry[1]))
        if not dialog.exec() or not dialog.crs().isValid():
            return
        srid = dialog.crs().postgisSrid()
        if not srid:
            show_error(self.dlg, tr('The selected CRS has no SRID.'))
            return
        self.run_task(
            tr('Updating SRID of "{0}"').format(info.name),
            lambda connection: admin_utils.update_srid(
                connection, info, geometry[0], srid),
            partial(
                self.report_result,
                tr('SRID of "{0}" set to {1}.').format(info.name, srid),
                tr('Updating the SRID failed!')))

    def force_geometry_type(self, geometry_type: str) -> None:
        info = self.selected()
        geometry = self.geometry_column(info) if info else None
        if geometry is None:
            return
        if not ask_question(
                self.dlg,
                tr('Change the geometry type of "{0}" to {1}?\n'
                   'Rows that cannot be converted will make the operation '
                   'fail.').format(info.name, geometry_type)):
            return
        self.run_task(
            tr('Changing geometry type of "{0}"').format(info.name),
            lambda connection: admin_utils.force_geometry_type(
                connection, info, geometry[0], geometry_type, geometry[1]),
            partial(
                self.report_result,
                tr('Geometry type of "{0}" changed to {1}.').format(
                    info.name, geometry_type),
                tr('Changing the geometry type failed!')))

    def build_overviews(self, max_level: int) -> None:
        info = self.selected()
        if info is None or not info.is_raster():
            return
        if info.overviews and not ask_question(
                self.dlg,
                tr('Existing overviews of "{0}" will be dropped and built '
                   'again. Continue?').format(info.name)):
            return
        self.run_task(
            tr('Building overviews of "{0}"').format(info.name),
            lambda connection: admin_utils.build_overviews(
                connection, info, max_level),
            partial(
                self.report_result,
                tr('Overviews of "{0}" built.').format(info.name),
                tr('Building overviews failed!')))

    def add_raster_constraints(self) -> None:
        info = self.selected()
        if info is None or not info.is_raster():
            return
        self.run_task(
            tr('Adding raster constraints to "{0}"').format(info.name),
            lambda connection: admin_utils.add_raster_constraints(
                connection, info),
            partial(
                self.report_result,
                tr('Raster constraints added to "{0}".').format(info.name),
                tr('Adding raster constraints failed!')))

    def retile(self, tile_size: int) -> None:
        info = self.selected()
        if info is None or not info.is_raster():
            return
        name = f'{info.name}_{tile_size}'
        if name in table_names_in_schema(self.tables, info.schema):
            show_error(self.dlg,
                       tr('Table "{0}" already exists.').format(name))
            return
        self.run_task(
            tr('Retiling "{0}"').format(info.name),
            lambda connection: admin_utils.retile(
                connection, info, tile_size, name),
            partial(
                self.report_result,
                tr('Retiled "{0}" into "{1}".').format(info.name, name),
                tr('Retiling failed!')))

    def edit_privileges(self) -> None:
        info = self.selected()
        if info is None:
            return
        roles = admin_utils.role_names(self.main.db)
        owner = admin_utils.table_owner(self.main.db, info) or ''
        self.privileges_dialog = PrivilegesDialog(
            info.qualified_name(), roles, owner, self.dlg)
        self.privileges_dialog.role_changed.connect(
            partial(self.load_role_privileges, info))
        self.privileges_dialog.apply_requested.connect(
            partial(self.apply_privileges, info))
        self.load_role_privileges(info, self.privileges_dialog.selected_role())
        self.privileges_dialog.exec()
        self.privileges_dialog = None
        self.show_details(info)

    def load_role_privileges(self, info: TableInfo, role: str) -> None:
        if self.privileges_dialog is None or not role:
            return
        self.privileges_dialog.set_privileges(
            admin_utils.role_privileges(self.main.db, info, role))

    def apply_privileges(self, info: TableInfo) -> None:
        dialog = self.privileges_dialog
        if dialog is None:
            return
        role = dialog.selected_role()
        current = admin_utils.role_privileges(self.main.db, info, role)
        wanted = dialog.checked_privileges()
        success = admin_utils.apply_privileges(
            self.main.db, info, role,
            sorted(wanted - current), sorted(current - wanted))
        owner = admin_utils.table_owner(self.main.db, info)
        if success and dialog.selected_owner() \
                and dialog.selected_owner() != owner:
            success = admin_utils.change_owner(
                self.main.db, info, dialog.selected_owner())
        if success:
            show_info(dialog, tr('Privileges of "{0}" updated.').format(
                info.name))
        else:
            show_error(dialog, tr('Updating privileges failed!'))
        self.load_role_privileges(info, role)

    def close(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
