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
 This script initializes the plugin, making it known to QGIS.
"""

__author__ = 'Eryk Chełchowski'
__date__ = '2022-05-12'
__copyright__ = '(C) 2022 by Eryk Chełchowski'


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load PostGISToolbox class from file PostGISToolbox.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .postgis_toolbox import PostGISToolboxPlugin
    return PostGISToolboxPlugin()
