# -*- coding: utf-8 -*-

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    get_table_geom_columns, get_table_columns, create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name


class PostGISToolboxVectorMakeValid(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    METHOD = 'METHOD'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'

    def initAlgorithm(self, config=None):
        self.input_layers_dict = get_all_vectors_from_project(True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        self.repair_methods = ['ST_Buffer', 'ST_MakeValid']
        if not get_main_plugin_class().db or not self.input_layers_dict:
            return
        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input layer'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=self.input_layers[0]))

        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD,
            tr('Repair method'),
            options=self.repair_methods,
            allowMultiple=False,
            defaultValue=self.repair_methods[0]))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'repaired_vectors'))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OVERWRITE,
            tr('Overwrite table if exists'),
            True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_TO_PROJECT,
            tr('Add result layer to the project'),
            True))

    def processAlgorithm(self, parameters, context, feedback):
        if not self.input_layers:
            QMessageBox.critical(
                iface.mainWindow(), plugin_name,
                tr('No PostGIS layers in the active project!'),
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}

        input_layer = self.input_layers_dict[
            self.input_layers[self.parameterAsEnum(
                parameters, self.INPUT, context)]]
        repair_method = self.repair_methods[
            self.parameterAsEnum(parameters, self.METHOD, context)]
        schema_name, table_name = get_pg_table_name_from_uri(
            input_layer.dataProvider().dataSourceUri()).split('.')
        uri = QgsDataSourceUri(input_layer.source())

        q_add_to_project = self.parameterAsBool(
            parameters, self.LOAD_TO_PROJECT, context)
        q_overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)
        schema_enum = self.parameterAsEnum(
            parameters, self.DEST_SCHEMA, context)
        out_schema = self.schemas_list[schema_enum]
        out_table = remove_unsupported_chars(
            self.parameterAsString(parameters, self.DEST_TABLE, context))

        if feedback.isCanceled():
            return {}

        input_columns = get_table_columns(
            self.db,
            schema_name,
            table_name,
            get_table_geom_columns(
                self.db,
                schema_name,
                table_name
            )
        )
        if feedback.isCanceled():
            return {}

        if self.db.isOpen() and self.db.isValid() \
                and make_query(self.db, test_query):
            if q_overwrite:
                make_query(self.db, f'DROP TABLE IF EXISTS '
                                    f'"{out_schema}"."{out_table}";')
            else:
                if check_table_exists_in_schema(
                        self.db, out_schema, out_table):
                    return {}

            if feedback.isCanceled():
                return {}

            geom_query = f'ST_Buffer(ST_Buffer(input_table."{uri.geometryColumn()}", 0.001), -0.001) ' \
                if repair_method == 'ST_Buffer' \
                else f'ST_MakeValid(input_table."{uri.geometryColumn()}")'

            make_query(
                self.db,
                f'''
                    CREATE TABLE "{out_schema}"."{out_table}" AS ( 
                        SELECT {', '.join(f'"input_table"."{elem}"' for elem in input_columns)},
                         {geom_query} AS "geom"
                        FROM "{schema_name}"."{table_name}" AS input_table
                    );
                '''
            )
            create_vector_geom_index(
                self.db, out_table, 'geom', schema=out_schema
            )

            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'{tr("Repaired")} {input_layer.name()}',
            geom_col='geom'
        )
        if feedback.isCanceled():
            return {}

        if q_add_to_project:
            add_vectors_to_project(PROCESSING_LAYERS_GROUP, [out_layer])

        return {
            self.OUTPUT: out_layer,
            self.DEST_SCHEMA: schema_enum,
            self.DEST_TABLE: out_table
        }

    def name(self):
        return 'repair_geometry'

    def displayName(self):
        return tr('Repair geometry')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorMakeValid()
