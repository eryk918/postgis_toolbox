# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PostGISToolbox
                                 A QGIS plugin
 Development of a QGIS plugin implementing selected PostGIS functions
                              -------------------
        begin                : 2022-05-12
        copyright            : (C) 2022 by Eryk Chełchowski
        email                : erwinek1998@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Eryk Chełchowski'
__date__ = '2022-05-12'
__copyright__ = '(C) 2022 by Eryk Chełchowski'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

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
        self.addAlgorithm(PostGISToolboxRasterSummary())
        self.addAlgorithm(PostGISToolboxRasterMerge())
        self.addAlgorithm(PostGISToolboxRasterResample())
        self.addAlgorithm(PostGISToolboxRasterTile())
        self.addAlgorithm(PostGISToolboxRasterClip())
        self.addAlgorithm(PostGISToolboxRasterReproject())

    def id(self):
        return plugin_dir_name

    def name(self):
        return tr('PostGIS Spatial Functions')

    def icon(self):
        return main_plugin_icon

    def longName(self):
        return self.name()
