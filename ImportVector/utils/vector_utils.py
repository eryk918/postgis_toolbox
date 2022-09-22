# -*- coding: utf-8 -*-
from qgis.core import QgsWkbTypes

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
