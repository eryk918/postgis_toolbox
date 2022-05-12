from qgis.PyQt.QtCore import QCoreApplication


def tr(string):
    return QCoreApplication.translate('Processing', string)