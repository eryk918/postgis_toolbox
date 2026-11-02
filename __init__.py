# -*- coding: utf-8 -*-

def classFactory(iface):
    from .postgis_toolbox import PostGISToolboxPlugin
    return PostGISToolboxPlugin()
