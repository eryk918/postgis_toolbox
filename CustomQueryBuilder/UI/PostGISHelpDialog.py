# -*- coding: utf-8 -*-
import os
from typing import Optional, List

import requests
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtWidgets import QWidget, QDialog

from ..query_utils import deprecated_functions, misspelled_functions_dict
from ...utils import repair_dialog

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'postgishelpdialog.ui'))


class PostGISHelpDialog(QDialog, FORM_CLASS):
    def __init__(self, main_class: callable,
                 parent: Optional[QWidget] = None) -> None:
        super(PostGISHelpDialog, self).__init__(parent)
        self.parent = main_class
        self.setupUi(self)
        self.setup_dialog()
        self.add_web_view_widget()

    def setup_dialog(self) -> None:
        repair_dialog(self, 'query_editor.png')

    def add_web_view_widget(self) -> None:
        try:
            from qgis.PyQt import QtWebEngineWidgets
            self.webEngineView = QtWebEngineWidgets.QWebEngineView()
        except ImportError:
            from qgis.PyQt import QtWebKitWidgets
            self.webEngineView = QtWebKitWidgets.QWebView()
        self.frame_web.layout().addWidget(self.webEngineView)
        self.function_cbbx.currentTextChanged.connect(self.set_address)

    def load_functions(self):
        self.function_cbbx.clear()
        self.function_cbbx.addItems(self.get_function_list())

    def get_function_list(self) -> List[str]:
        functions = []
        for func_name_id in range(self.parent.functions.count()):
            func_name = self.parent.functions.itemText(func_name_id).strip('(')
            if func_name in deprecated_functions or func_name_id == 0:
                continue
            if misspelled_functions_dict.get(func_name):
                func_name = misspelled_functions_dict[func_name]
            functions.append(func_name)
        return functions

    def set_address(self) -> None:
        function = self.function_cbbx.currentText()
        address = f'https://postgis.net/docs/{function}.html'
        tmp = requests.get(address, verify=False).text
        if '404 Not Found' in tmp:
            address = f'https://postgis.net/docs/RT_{function}.html'
        self.webEngineView.setUrl(QUrl(address))

    def run(self) -> None:
        self.load_functions()
        self.set_address()
        self.show()
