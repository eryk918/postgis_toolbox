# -*- coding: utf-8 -*-
from qgis.core import QgsWkbTypes, QgsVectorLayer

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
