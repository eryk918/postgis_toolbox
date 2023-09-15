# -*- coding: utf-8 -*-
from typing import Dict, List, Any

from plugins.processing.gui.wrappers import WidgetWrapper
from qgis.PyQt.QtWidgets import QMessageBox, QWidget, QVBoxLayout, QComboBox, \
    QCheckBox, QLabel
from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterBoolean, \
    QgsProcessingParameterString, QgsDataSourceUri,QgsProcessingParameterEnum, \
    QgsProcessingParameterNumber
from qgis.gui import QgsCheckableComboBox
from qgis.utils import iface

from .vec_alg_utils import get_pg_table_name_from_uri, \
    create_vector_geom_index, check_table_exists_in_schema, \
    check_db_connection, get_table_columns, get_table_geom_columns
from ..utils import get_plugin_object, make_query, test_query, tr, \
    add_vectors_to_project, create_postgis_vector_layer, \
    get_schema_name_list, PROCESSING_LAYERS_GROUP, \
    get_all_vectors_from_project, remove_unsupported_chars, plugin_name, \
    plugin_dir_name


class CustomWidgetLayout(WidgetWrapper):

    def createWidget(self):
        self.db = get_plugin_object().db
        self.input_layers_dict = get_all_vectors_from_project(True)
        self.input_layers = list(self.input_layers_dict.keys()) \
            if self.input_layers_dict else []
        editor = QWidget()
        layout = QVBoxLayout()
        self.input_layers_combo = QComboBox()
        self.input_layer_checkbox = QCheckBox(tr('Only selected features'))
        self.input_layers_columns_combo = QgsCheckableComboBox()
        self.input_layers_combo.currentTextChanged.connect(
            lambda text: self.get_columns_for_lyr(text,
                                                  self.input_layers_columns_combo))
        self.input_layers_combo.addItems(self.input_layers)
        layout.addWidget(self.input_layers_combo)
        layout.addWidget(self.input_layer_checkbox)
        layout.addWidget(QLabel(tr('Choose columns from input layer')))
        layout.addWidget(self.input_layers_columns_combo)
        layout.setContentsMargins(0, 0, 0, 0)
        editor.setLayout(layout)
        return editor

    def get_columns_for_lyr(self, combo_text: str,
                            target_combo: QgsCheckableComboBox) -> None:
        lyr = self.input_layers_dict.get(combo_text)
        schema, table = get_pg_table_name_from_uri(
            lyr.dataProvider().dataSourceUri()).split('.')
        col_list = get_table_columns(self.db, schema, table,
                                     get_table_geom_columns(self.db, schema,
                                                            table))
        target_combo.clear()
        target_combo.addItems(col_list)

    def value(self):
        return self.input_layers_combo.currentText(), self.input_layer_checkbox.isChecked(), self.input_layers_columns_combo.checkedItems()


class PostGISToolboxVectorBuffer(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    INPUT = 'INPUT'
    CUSTOM_WIDGET = 'CUSTOM_WIDGET'
    BUFFER_SIZE = 'BUFFER_SIZE'
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

        if not get_plugin_object().db or not self.input_layers_dict:
            return

        self.db = get_plugin_object().db
        self.schemas_list, _ = get_schema_name_list(self.db, change_db=False)
        default_schema = self.schemas_list[0] if self.schemas_list else None

        param = QgsProcessingParameterString(self.CUSTOM_WIDGET,
                                             tr('Input layer'))
        param.setMetadata({
            'widget_wrapper': {
                'class': CustomWidgetLayout}})
        self.addParameter(param)

        self.addParameter(QgsProcessingParameterNumber(
            name=self.BUFFER_SIZE,
            description=tr('Buffer size'),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=10,
            minValue=0,
            maxValue=99999)
        )
        self.addParameter(QgsProcessingParameterEnum(
            self.DEST_SCHEMA,
            tr("Output schema"),
            options=self.schemas_list,
            allowMultiple=False,
            defaultValue=default_schema))

        self.addParameter(QgsProcessingParameterString(
            self.DEST_TABLE, tr('Output table name'), 'buffer'))

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
        input_lyr_name, input_selected, input_columns = parameters.get(
            self.CUSTOM_WIDGET)
        input_vector_layer = self.input_layers_dict.get(input_lyr_name)
        input_layer_info_dict = {
            'schema_name': get_pg_table_name_from_uri(
                input_vector_layer.dataProvider().dataSourceUri()).split('.')[
                0],
            'table_name': get_pg_table_name_from_uri(
                input_vector_layer.dataProvider().dataSourceUri()).split('.')[
                1],
            'srid': input_vector_layer.crs().postgisSrid(),
            'uri': QgsDataSourceUri(input_vector_layer.source()), }
        q_add_to_project = self.parameterAsBool(
            parameters, self.LOAD_TO_PROJECT, context)
        q_overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)
        schema_enum = self.parameterAsEnum(
            parameters, self.DEST_SCHEMA, context)
        buffer_size = self.parameterAsDouble(
            parameters, self.BUFFER_SIZE, context)
        out_schema = self.schemas_list[schema_enum]
        out_table = remove_unsupported_chars(
            self.parameterAsString(parameters, self.DEST_TABLE, context))
        if not input_columns:
            input_columns = get_table_columns(
                self.db,
                input_layer_info_dict['schema_name'],
                input_layer_info_dict['table_name'],
                get_table_geom_columns(
                    self.db,
                    input_layer_info_dict['schema_name'],
                    input_layer_info_dict['table_name']
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
            make_query(
                self.db,
                self.generate_buffer_query(
                    out_table, out_schema, input_layer_info_dict,
                    input_columns, buffer_size
                )
            )
            create_vector_geom_index(self.db, out_table, 'geom',
                                     schema=out_schema)
            if feedback.isCanceled():
                return {}

        out_layer = create_postgis_vector_layer(
            self.db,
            out_schema,
            out_table,
            layer_name=f'{tr("Buffer")} {input_vector_layer.name()}',
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

    def generate_buffer_query(
            self, out_table: str, out_schema: str,
            input_layer_info_dict: Dict[str, Any],
            input_columns: List[str], buffer_size: float) -> str:

        selected_columns = ', '.join(
            f'"input_table"."{elem}"'
            for elem in input_columns
        )
        return f'''
            CREATE TABLE "{out_schema}"."{out_table}" AS ( 
                SELECT {selected_columns},
                 ST_Buffer(input_table."{input_layer_info_dict['uri'].geometryColumn()}",
                        {buffer_size}) AS "geom"
                FROM "{input_layer_info_dict['schema_name']}"."{input_layer_info_dict['table_name']}" 
                    AS input_table
            );
        '''

    def name(self):
        return 'vector_buffer'

    def displayName(self):
        return tr('Buffer')

    def group(self):
        return tr(self.groupId())

    def groupId(self):
        return tr('Vector')

    def createInstance(self):
        return PostGISToolboxVectorBuffer()
