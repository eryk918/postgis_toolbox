# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from qgis.PyQt.QtCore import QMimeData, pyqtSignal
from qgis.PyQt.QtGui import QDrag
from qgis.PyQt.QtWidgets import QTableWidget, QAbstractItemView
from qgis.core import QgsMimeDataUtils

LAYER_URI_ROLE = Qt.UserRole + 1


class TableRegistryView(QTableWidget):
    delete_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete and not event.modifiers():
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mimeData(self, items) -> QMimeData:
        uris = []
        for item in items:
            if item.column() != 0:
                continue
            for provider, uri, name in item.data(LAYER_URI_ROLE) or []:
                layer_uri = QgsMimeDataUtils.Uri()
                layer_uri.layerType = 'raster' \
                    if provider == 'postgresraster' else 'vector'
                layer_uri.providerKey = provider
                layer_uri.uri = uri
                layer_uri.name = name
                uris.append(layer_uri)
        if not uris:
            return super().mimeData(items)
        return QgsMimeDataUtils.encodeUriList(uris)

    def startDrag(self, actions) -> None:
        data = self.mimeData(self.selectedItems())
        if data is None:
            return
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.exec(Qt.CopyAction)
