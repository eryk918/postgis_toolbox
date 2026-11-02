# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import Qgis, QgsProject

from .UI.projects_dialog import ProjectsDialog
from .utils.project_utils import list_projects, delete_project, \
    project_uri, project_schemas, project_storage, DEFAULT_SCHEMA
from ..utils import iface, tr, check_connection, show_error, ask_question, \
    get_active_db_info, plugin_name, Qt, read_setting, save_setting

SCHEMA_SETTING = 'projects/schema'


class Projects:
    def __init__(self, parent) -> None:
        self.main = parent
        self.dlg = None

    def run(self) -> None:
        if not check_connection(self.main.db):
            show_error(
                iface.mainWindow(),
                tr('No connection to a PostGIS database.'))
            return
        if project_storage() is None:
            show_error(
                iface.mainWindow(),
                tr('This QGIS build has no PostgreSQL project storage.'))
            return
        if self.dlg is None:
            self.dlg = ProjectsDialog(self, iface.mainWindow())
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
        if not self.main.db:
            self.dlg.fill_schemas([], '')
            self.dlg.fill([])
            return
        wanted = self.dlg.schema() or \
            read_setting(SCHEMA_SETTING, DEFAULT_SCHEMA) or DEFAULT_SCHEMA
        self.dlg.fill_schemas(project_schemas(self.main.db), wanted)
        self.load_projects()

    def load_projects(self) -> None:
        schema = self.dlg.schema()
        if not schema or not check_connection(self.main.db):
            self.dlg.fill([])
            return
        save_setting(SCHEMA_SETTING, schema)
        self.dlg.fill(list_projects(self.main.db, schema))

    def selected(self) -> str:
        name = self.dlg.selected_project()
        if name is None or not check_connection(self.main.db):
            return ''
        return name

    def open_project(self) -> None:
        name = self.selected()
        if not name:
            return
        project = QgsProject.instance()
        if project.isDirty() and not ask_question(
                self.dlg,
                tr('The current project has unsaved changes.\n'
                   'Open "{0}" anyway?').format(name)):
            return
        if not iface.addProject(
                project_uri(self.main.db, self.dlg.schema(), name)):
            show_error(self.dlg,
                       tr('Opening the project "{0}" failed.').format(name))

    def default_name(self) -> str:
        project = QgsProject.instance()
        if project.title():
            return project.title()
        base = os.path.splitext(os.path.basename(project.fileName()))[0]
        return base or tr('project')

    def save_project(self) -> None:
        schema = self.dlg.schema()
        if not schema or not check_connection(self.main.db):
            return
        name, accepted = QInputDialog.getText(
            self.dlg, plugin_name, tr('Name of the project in the database'),
            text=self.default_name())
        name = name.strip()
        if not accepted or not name:
            return
        existing = [row[0] for row in list_projects(self.main.db, schema)]
        if name in existing and not ask_question(
                self.dlg,
                tr('Project "{0}" already exists. Overwrite it?').format(
                    name)):
            return
        if not QgsProject.instance().write(
                project_uri(self.main.db, schema, name)):
            show_error(self.dlg,
                       tr('Saving the project to the database failed.'))
            return
        iface.messageBar().pushMessage(
            plugin_name,
            tr('Project "{0}" saved to the database.').format(name),
            Qgis.Success, 3)
        self.load_projects()
        self.dlg.select_project(name)

    def delete_project(self) -> None:
        name = self.selected()
        if not name:
            return
        if not ask_question(
                self.dlg,
                tr('Delete the project "{0}" from the database?').format(
                    name)):
            return
        if not delete_project(self.main.db, self.dlg.schema(), name):
            show_error(self.dlg, tr('Deleting the project failed.'))
        self.load_projects()

    def close(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
