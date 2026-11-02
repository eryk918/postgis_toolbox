# -*- coding: utf-8 -*-
import os
from typing import Optional, List

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.PyQt.QtWidgets import QWidget, QDialog
from qgis.core import QgsNetworkAccessManager

from ..utils.query_utils import deprecated_functions, \
    misspelled_functions_dict, function_doc_url, raster_function_doc_url
from ...utils import repair_dialog

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'postgishelpdialog.ui'))


def create_web_view() -> Optional[QWidget]:
    try:
        from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
        return QWebEngineView()
    except ImportError:
        pass
    try:
        from qgis.PyQt.QtWebKitWidgets import QWebView
        return QWebView()
    except ImportError:
        return None


class PostGISHelpDialog(QDialog, FORM_CLASS):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        repair_dialog(self, 'query_editor.svg')
        self.reply = None
        self.web_view = create_web_view()
        if self.web_view is not None:
            self.frame_web.layout().addWidget(self.web_view)
        self.function_cbbx.currentTextChanged.connect(self.show_function_doc)

    def load_functions(self, functions: List[str]) -> None:
        names = []
        for function_name in functions:
            function_name = function_name.strip('(')
            if function_name in deprecated_functions:
                continue
            names.append(
                misspelled_functions_dict.get(function_name, function_name))
        self.function_cbbx.blockSignals(True)
        self.function_cbbx.clear()
        self.function_cbbx.addItems(names)
        self.function_cbbx.blockSignals(False)

    def show_function_doc(self, function_name: str) -> None:
        if not function_name:
            return
        if self.reply is not None:
            self.reply.abort()
        self.reply = QgsNetworkAccessManager.instance().get(
            QNetworkRequest(QUrl(function_doc_url(function_name))))
        self.reply.finished.connect(
            lambda: self.doc_check_finished(function_name))

    def doc_check_finished(self, function_name: str) -> None:
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        reply.deleteLater()
        if reply.error() == QNetworkReply.OperationCanceledError:
            return
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if status == 404 or b'404 Not Found' in bytes(reply.readAll()):
            self.open_url(raster_function_doc_url(function_name))
        else:
            self.open_url(function_doc_url(function_name))

    def open_url(self, address: str) -> None:
        if self.web_view is None:
            QDesktopServices.openUrl(QUrl(address))
        else:
            self.web_view.setUrl(QUrl(address))

    def run(self, functions: List[str]) -> None:
        self.load_functions(functions)
        self.show()
        self.show_function_doc(self.function_cbbx.currentText())
