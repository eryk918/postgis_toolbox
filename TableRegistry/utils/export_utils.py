# -*- coding: utf-8 -*-
from typing import Optional, Tuple

from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsVectorFileWriter, \
    QgsCoordinateTransform, QgsProject, QgsRasterFileWriter, QgsRasterPipe, \
    QgsRasterNuller, QgsRasterProjector, QgsMapLayer
from qgis.gui import QgsVectorLayerSaveAsDialog, QgsRasterLayerSaveAsDialog


def export_vector(layer: QgsVectorLayer,
                  parent: QWidget) -> Tuple[Optional[bool], str, Optional[QgsMapLayer]]:
    dialog = QgsVectorLayerSaveAsDialog(
        layer, QgsVectorLayerSaveAsDialog.Options(
            QgsVectorLayerSaveAsDialog.Option.AllOptions), parent)
    if not dialog.exec():
        return None, '', None
    project = QgsProject.instance()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = dialog.format()
    options.layerName = dialog.layerName()
    options.actionOnExistingFile = dialog.creationActionOnExistingFile()
    options.fileEncoding = dialog.encoding()
    options.datasourceOptions = dialog.datasourceOptions()
    options.layerOptions = dialog.layerOptions()
    options.symbologyExport = dialog.symbologyExport()
    options.symbologyScale = dialog.scale()
    options.attributes = dialog.selectedAttributes()
    options.forceMulti = dialog.forceMulti()
    options.includeZ = dialog.includeZ()
    options.overrideGeometryType = dialog.geometryType()
    if dialog.crs().isValid():
        options.ct = QgsCoordinateTransform(
            layer.crs(), dialog.crs(), project.transformContext())
    if dialog.hasFilterExtent():
        options.filterExtent = dialog.filterExtent()
    if dialog.persistMetadata():
        options.saveMetadata = True
        options.layerMetadata = layer.metadata()
    error, message, new_file, new_layer = \
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, dialog.fileName(), project.transformContext(), options)
    if error != QgsVectorFileWriter.NoError:
        return False, message, None
    if not dialog.addToCanvas():
        return True, new_file, None
    source = new_file if not new_layer else f'{new_file}|layername={new_layer}'
    return True, new_file, QgsVectorLayer(source, dialog.layerName()
                                          or layer.name(), 'ogr')


def export_raster(layer: QgsRasterLayer,
                  parent: QWidget) -> Tuple[Optional[bool], str, Optional[QgsMapLayer]]:
    provider = layer.dataProvider()
    dialog = QgsRasterLayerSaveAsDialog(
        layer, provider, layer.extent(), layer.crs(),
        QgsProject.instance().crs(), parent)
    if not dialog.exec():
        return None, '', None
    context = QgsProject.instance().transformContext()
    writer = QgsRasterFileWriter(dialog.outputFileName())
    writer.setOutputFormat(dialog.outputFormat())
    if dialog.tileMode():
        writer.setTiledMode(True)
        writer.setMaxTileWidth(dialog.maximumTileSizeX())
        writer.setMaxTileHeight(dialog.maximumTileSizeY())
    writer.setBuildPyramidsFlag(dialog.buildPyramidsFlag())
    writer.setPyramidsList(dialog.pyramidsList())
    writer.setPyramidsResampling(dialog.pyramidsResamplingMethod())
    writer.setPyramidsFormat(dialog.pyramidsFormat())
    writer.setPyramidsConfigOptions(dialog.pyramidsConfigOptions())
    writer.setCreateOptions(dialog.createOptions())
    if dialog.mode() == QgsRasterLayerSaveAsDialog.RawDataMode:
        pipe = QgsRasterPipe()
        pipe.set(provider.clone())
        nuller = QgsRasterNuller()
        for band in range(1, provider.bandCount() + 1):
            nuller.setNoData(band, dialog.noData())
        pipe.insert(1, nuller)
    else:
        pipe = QgsRasterPipe(layer.pipe())
    if dialog.outputCrs() != layer.crs():
        if pipe.projector() is None:
            pipe.insert(2, QgsRasterProjector())
        pipe.projector().setCrs(layer.crs(), dialog.outputCrs(), context)
    error = writer.writeRaster(
        pipe, dialog.nColumns(), dialog.nRows(), dialog.outputRectangle(),
        dialog.outputCrs(), context)
    if error != QgsRasterFileWriter.NoError:
        return False, str(error), None
    if not dialog.addToCanvas():
        return True, dialog.outputFileName(), None
    return True, dialog.outputFileName(), QgsRasterLayer(
        dialog.outputFileName(), layer.name(), 'gdal')
