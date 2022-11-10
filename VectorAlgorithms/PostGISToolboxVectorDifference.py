# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum, QgsWkbTypes)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    get_table_geom_columns, get_table_columns, create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name


class PostGISToolboxVectorDifference(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    INPUT_DIFF = 'INPUT_DIFF'
    FIELDS_INPUT = 'FIELDS_INPUT'
    FIELDS_DIFF = 'FIELDS_DIFF'
    DEST_TABLE = 'DEST_TABLE'
    DEST_SCHEMA = 'DEST_SCHEMA'
    SINGLE = 'SINGLE'
    LOAD_TO_PROJECT = 'LOAD_TO_PROJECT'
    OVERWRITE = 'OVERWRITE'
    KEEP = 'KEEP'
    OPTIONS = 'OPTIONS'

    def initAlgorithm(self, config=None):
        self.input_layers_dict = get_all_vectors_from_project(True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        default_layer = self.input_layers[0] if self.input_layers else None

        if not get_main_plugin_class().db or not self.input_layers_dict:
            return

        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input layer'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=self.input_layers[0]))

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT_DIFF,
            tr('Layer to be subtracted'),
            options=self.input_layers,
            allowMultiple=False,
            defaultValue=default_layer))

        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_layer))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'difference'))

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
                'No PostGIS layers in the active project!',
                QMessageBox.Ok)
            return {}
        elif not check_db_connection(self, 'schemas_list'):
            return {}

        input_layer_a = self.input_layers_dict[
            self.input_layers[self.parameterAsEnum(
                parameters, self.INPUT, context)]]
        schema_name_a, table_name_a = get_pg_table_name_from_uri(
            input_layer_a.dataProvider().dataSourceUri()).split('.')
        srid_a = input_layer_a.crs().postgisSrid()
        uri_a = QgsDataSourceUri(input_layer_a.source())
        geom_col_a = uri_a.geometryColumn()
        geom_type_a = input_layer_a.geometryType()

        input_layer_b = self.input_layers_dict[
            self.input_layers[self.parameterAsEnum(
                parameters, self.INPUT_DIFF, context)]]
        schema_name_b, table_name_b = get_pg_table_name_from_uri(
            input_layer_b.dataProvider().dataSourceUri()).split('.')
        uri_b = QgsDataSourceUri(input_layer_b.source())
        geom_col_b = uri_b.geometryColumn()
        srid_b = input_layer_b.crs().postgisSrid()

        q_single_type = self.parameterAsBool(parameters, self.SINGLE, context)
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

        if geom_type_a == QgsWkbTypes.PointGeometry:
            out_geom_type = "POINT"
        elif geom_type_a == QgsWkbTypes.LineGeometry:
            out_geom_type = "LINESTRING"
        else:
            out_geom_type = "POLYGON"

        if not q_single_type:
            out_geom_type = f"MULTI{out_geom_type}"

        columns = get_table_columns(
            self.db,
            schema_name_a,
            table_name_a,
            get_table_geom_columns(
                self.db,
                schema_name_a,
                table_name_a
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
                if check_table_exists_in_schema(self.db, out_schema,
                                                out_table):
                    return {}
            if feedback.isCanceled():
                return {}

            union_geom_part = f"""
                WITH union_geom AS (
                    SELECT ST_Union("{geom_col_b}") AS geom
                FROM "{schema_name_b}"."{table_name_b}"
                )
            """

            geom_b_part = f'g2."geom"'
            if srid_b != srid_a:
                geom_b_part = f'ST_Transform(g2."{geom_col_b}", {srid_a})'
            geom_query_part = f'(ST_Multi(ST_Difference(g1."{geom_col_a}"' \
                              f', {geom_b_part})))::geometry({out_geom_type}' \
                              f', {srid_a}) AS geom'
            if q_single_type:
                geom_query_part = f'(ST_Difference(g1."{geom_col_a}", ' \
                                  f'{geom_b_part}))::geometry(' \
                                  f'{out_geom_type}, {srid_a}) AS geom'

            make_query(self.db, f'''
              CREATE TABLE "{out_schema}"."{out_table}" AS (
                  {union_geom_part}
                  SELECT g1."{'", g1."'.join(columns)}", {geom_query_part}
                  FROM "{schema_name_a}"."{table_name_a}" AS g1, 
                      union_geom AS g2 
              );
            ''')
            create_vector_geom_index(self.db, out_table, 'geom')
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'{tr("Subtracted")} {input_layer_a.name()}',
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
        return 'difference'

    def displayName(self):
        return tr('Difference')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return 'Vector'

    def createInstance(self):
        return PostGISToolboxVectorDifference()
