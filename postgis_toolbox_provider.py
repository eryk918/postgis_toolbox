# -*- coding: utf-8 -*-

import os

from qgis.core import QgsProcessingProvider

from .VectorAlgorithms.PostGISToolboxVectorMakeValid import PostGISToolboxVectorMakeValid
from .VectorAlgorithms.PostGISToolboxVectorGeneraterPolygonByPoints import PostGISToolboxVectorGeneratePolygonFromPoints
from .VectorAlgorithms.PostGISToolboxVectorAggregate import PostGISToolboxVectorAggregate
from .VectorAlgorithms.PostGISToolboxVectorGeneratePoints import PostGISToolboxVectorGeneratePoints
from .VectorAlgorithms.PostGISToolboxVectorIntersect import PostGISToolboxVectorIntersects
from .VectorAlgorithms.PostGISToolboxVectorBuffer import PostGISToolboxVectorBuffer
from .RasterAlgorithms.PostGISToolboxRasterClip import PostGISToolboxRasterClip
from .RasterAlgorithms.PostGISToolboxRasterSummary import PostGISToolboxRasterSummary
from .RasterAlgorithms.PostGISToolboxRasterTile import PostGISToolboxRasterTile
from .RasterAlgorithms.PostGISToolboxRasterMerge import PostGISToolboxRasterMerge
from .RasterAlgorithms.PostGISToolboxRasterResample import PostGISToolboxRasterResample
from .RasterAlgorithms.PostGISToolboxRasterReproject import PostGISToolboxRasterReproject
from .VectorAlgorithms.PostGISToolboxVectorClip import PostGISToolboxVectorClip
from .VectorAlgorithms.PostGISToolboxVectorDifference import \
    PostGISToolboxVectorDifference
from .VectorAlgorithms.PostGISToolboxVectorMerge import \
    PostGISToolboxVectorMerge
from .VectorAlgorithms.PostGISToolboxVectorNearestNeighbor import \
    PostGISToolboxVectorNearestNeighbor
from .VectorAlgorithms.PostGISToolboxVectorCluster import \
    PostGISToolboxVectorCluster
from .VectorAlgorithms.PostGISToolboxVectorSimplify import \
    PostGISToolboxVectorSimplify
from .VectorAlgorithms.PostGISToolboxVectorVoronoi import \
    PostGISToolboxVectorVoronoi
from .VectorAlgorithms.PostGISToolboxVectorCentroids import \
    PostGISToolboxVectorCentroids
from .VectorAlgorithms.PostGISToolboxVectorDissolve import \
    PostGISToolboxVectorDissolve
from .RasterAlgorithms.PostGISToolboxRasterTerrain import \
    PostGISToolboxRasterTerrain
from .RasterAlgorithms.PostGISToolboxRasterVectorize import \
    PostGISToolboxRasterVectorize
from .RasterAlgorithms.PostGISToolboxRasterZonalStatistics import \
    PostGISToolboxRasterZonalStatistics
from .utils import tr, plugin_dir_name, main_plugin_icon

pluginPath = os.path.dirname(__file__)


class PostGISToolboxProvider(QgsProcessingProvider):

    def __init__(self, main_class):
        QgsProcessingProvider.__init__(self)
        self.main_class = main_class

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(PostGISToolboxVectorClip())
        self.addAlgorithm(PostGISToolboxVectorDifference())
        self.addAlgorithm(PostGISToolboxVectorIntersects())
        self.addAlgorithm(PostGISToolboxVectorMakeValid())
        self.addAlgorithm(PostGISToolboxVectorGeneratePoints())
        self.addAlgorithm(PostGISToolboxVectorGeneratePolygonFromPoints())
        self.addAlgorithm(PostGISToolboxVectorAggregate())
        self.addAlgorithm(PostGISToolboxVectorBuffer())
        self.addAlgorithm(PostGISToolboxVectorMerge())
        self.addAlgorithm(PostGISToolboxVectorNearestNeighbor())
        self.addAlgorithm(PostGISToolboxVectorCluster())
        self.addAlgorithm(PostGISToolboxVectorSimplify())
        self.addAlgorithm(PostGISToolboxVectorVoronoi())
        self.addAlgorithm(PostGISToolboxVectorCentroids())
        self.addAlgorithm(PostGISToolboxVectorDissolve())
        self.addAlgorithm(PostGISToolboxRasterSummary())
        self.addAlgorithm(PostGISToolboxRasterMerge())
        self.addAlgorithm(PostGISToolboxRasterResample())
        self.addAlgorithm(PostGISToolboxRasterTile())
        self.addAlgorithm(PostGISToolboxRasterClip())
        self.addAlgorithm(PostGISToolboxRasterReproject())
        self.addAlgorithm(PostGISToolboxRasterTerrain())
        self.addAlgorithm(PostGISToolboxRasterVectorize())
        self.addAlgorithm(PostGISToolboxRasterZonalStatistics())

    def id(self):
        return plugin_dir_name

    def name(self):
        return tr('PostGIS Spatial Functions')

    def icon(self):
        return main_plugin_icon

    def longName(self):
        return self.name()
