# -*- coding: utf-8 -*-
from typing import Dict, Any

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString, QgsDataSourceUri,
                       QgsProcessingParameterEnum, QgsWkbTypes)
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    create_vector_geom_index, \
    check_table_exists_in_schema, check_db_connection, get_table_columns, \
    get_table_geom_columns
from ..utils import get_main_plugin_class, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    plugin_dir_name


class PostGISToolboxVectorMerge(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
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

        if not get_main_plugin_class().db or not self.input_layers_dict:
            return

        self.db = get_main_plugin_class().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        self.addParameter(QgsProcessingParameterEnum(
            self.INPUT,
            tr('Input layers'),
            options=self.input_layers,
            allowMultiple=True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.SINGLE, tr('Force output as singlepart'), False))

        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'merge'))

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

        layers_list = [self.input_layers_dict[self.input_layers[layer_id]]
                       for layer_id in parameters[self.INPUT]]

        first_layer_name = layers_list[0].name()

        layers_dict = {}
        geom_set = set()
        srid_set = set()
        for layer in layers_list:
            tmp_dict = {
                'schema_name': get_pg_table_name_from_uri(
                    layer.dataProvider().dataSourceUri()).split('.')[0],
                'table_name': get_pg_table_name_from_uri(
                    layer.dataProvider().dataSourceUri()).split('.')[1],
                'srid': layer.crs().postgisSrid(),
                'uri': QgsDataSourceUri(layer.source())
            }
            tmp_dict['geom_col'] = tmp_dict['uri'].geometryColumn()
            tmp_dict['geom_type'] = layer.geometryType()
            geom_set.add(tmp_dict['geom_type'])
            srid_set.add(tmp_dict['srid'])
            layers_dict[layer.name()] = tmp_dict

        if len(geom_set) > 1:
            return {}
        else:
            geom_type = list(geom_set)[0]
            base_srid = list(srid_set)[0]

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

        if geom_type == QgsWkbTypes.PointGeometry:
            out_geom_type = "POINT"
        elif geom_type == QgsWkbTypes.LineGeometry:
            out_geom_type = "LINESTRING"
        else:
            out_geom_type = "POLYGON"

        if not q_single_type:
            out_geom_type = f"MULTI{out_geom_type}"

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

            make_query(
                self.db,
                self.generate_merge_query(
                    out_table, out_schema,
                    layers_dict, base_srid,
                    q_single_type, out_geom_type
                )
            )
            create_vector_geom_index(self.db, out_table, 'geom')
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'{tr("Merged")} {first_layer_name}',
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

    def generate_merge_query(
            self, out_table: str, out_schema: str,
            layers_dict: Dict[str, Any], base_srid: int,
            q_single_type: bool, out_geom_type: str) -> str:

        query = f'CREATE TABLE "{out_schema}"."{out_table}" AS('
        table_ord_number = 1
        for layer_name, layer_info_dict in layers_dict.items():
            schema, table, srid, uri, geom_col, geom_type = \
                layer_info_dict.values()
            columns = get_table_columns(
                self.db,
                schema,
                table,
                get_table_geom_columns(
                    self.db,
                    schema,
                    table
                )
            )
            geom_part = f'g{table_ord_number}."{geom_col}"'
            if base_srid != srid:
                geom_part = f'ST_Transform({geom_part}, {base_srid})'
            geom_query_part = f'{geom_part} AS geom'

            if q_single_type:
                geom_query_part = \
                    f'(ST_Dump({geom_part})).geom::geometry(' \
                    f'{out_geom_type}, {base_srid}) AS geom'

            query += f'''
                SELECT g{table_ord_number}."{f'", g{table_ord_number}."'.join(columns)}", 
                    {geom_query_part} 
                FROM "{schema}"."{table}" AS g{table_ord_number}
            '''
            if list(layers_dict.keys()).index(layer_name) != \
                    len(list(layers_dict.keys())) - 1:
                query += " UNION "
            table_ord_number += 1
        query += ");"

        return query

    def name(self):
        return 'vector_merge'

    def displayName(self):
        return tr('Merge')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorMerge()
