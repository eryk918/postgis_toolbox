# -*- coding: utf-8 -*-
from qgis.core import QgsWkbTypes

vector_extensions = [
    'shp',
    'gpkg',
    'dbf'
]

none_geometry_types = (
    QgsWkbTypes.Unknown,
    QgsWkbTypes.UnknownGeometry,
    QgsWkbTypes.NoGeometry,
    QgsWkbTypes.NullGeometry
)
