# -*- coding: utf-8 -*-
import tempfile

from qgis.core import QgsWkbTypes, QgsVectorLayer, QgsVectorFileWriter, \
    QgsCoordinateTransformContext

vector_extensions = [
    'shp',
    'gpkg',
    'dbf',
    'xml'
]

simple_vector_extensions = [
    'shp',
    'dbf',
]

none_geometry_types = (
    QgsWkbTypes.Unknown,
    QgsWkbTypes.NoGeometry,
    QgsWkbTypes.NullGeometry
)


def make_sql_set_geometry_srid(table: str, schema: str, layer_path: str,
                               geom_column: str = 'geom') -> str:
    layer = QgsVectorLayer(layer_path)
    if layer.isValid() and layer.crs().postgisSrid():
        crs = layer.crs().postgisSrid()
        del layer
        return f'UPDATE "{schema}"."{table}" ' \
               f'SET {geom_column}=ST_SetSRID({geom_column}, {crs});'
    return 'SELECT 1;'


def check_for_duplicate_id_column(input_layer_path: str) -> str:
    out_file_path = input_layer_path
    tmp_layer = QgsVectorLayer(input_layer_path, 'temp', "ogr")
    fields_list = {
        field.name().lower(): field.name()
        for field in tmp_layer.fields().toList()
    }
    if fields_list.get('id'):
        out_file_path = f'{tempfile.NamedTemporaryFile().name}.gpkg'
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = 'GPKG'
        QgsVectorFileWriter.writeAsVectorFormatV2(
            tmp_layer, out_file_path, QgsCoordinateTransformContext(),
            save_options
        )
        del tmp_layer

        tmp_layer = QgsVectorLayer(out_file_path, 'temp', "ogr")
        field_name = fields_list.get('id')
        tmp_layer.startEditing()
        tmp_layer.renameAttribute(
            tmp_layer.fields().indexFromName(field_name),
            f'old_{field_name}'
        )
        tmp_layer.commitChanges()
    return out_file_path
