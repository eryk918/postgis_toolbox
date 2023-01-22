# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialogButtonBox

from .PostGISHelpDialog import PostGISHelpDialog
from ...utils import tr


class CustomQueryBuilderDialog(object):
    def __init__(self, main_class):
        self.main_class = main_class

    def setupUi(self, dialog_instance):
        dialog_instance.setObjectName("CustomQueryBuilderDialog")
        dialog_instance.resize(800, 470)
        self.create_widgets(dialog_instance)
        self.retranslateUi(dialog_instance)
        self.setup_actions(dialog_instance)

    def _create_layouts(self, dialog_instance) -> None:
        self.verticalLayout_7 = QtWidgets.QVBoxLayout(dialog_instance)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.horizontalLayout_6 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_6.setSizeConstraint(
            QtWidgets.QLayout.SetDefaultConstraint)
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.formLayout.setLabelAlignment(
            QtCore.Qt.AlignLeading | QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.formLayout.setObjectName("formLayout")
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.group.sizePolicy().hasHeightForWidth())
        self.group.setSizePolicy(sizePolicy)
        self.group.setMaximumSize(QtCore.QSize(16777215, 25))
        self.group.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.group.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.group.setObjectName("group")
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.order.sizePolicy().hasHeightForWidth())
        self.verticalLayout_4 = QtWidgets.QVBoxLayout()
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.order.setSizePolicy(sizePolicy)
        self.order.setMaximumSize(QtCore.QSize(16777215, 25))
        self.order.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.order.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.order.setObjectName("order")
        self.verticalLayout_5 = QtWidgets.QVBoxLayout(self.page)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.line_2 = QtWidgets.QFrame(self.page)
        self.line_2.setFrameShape(QtWidgets.QFrame.HLine)
        self.line_2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.line_2.setObjectName("line_2")
        self.helper_frame = QtWidgets.QFrame()
        self.helper_frame.setLayout(QtWidgets.QHBoxLayout())
        self.verticalLayout_6 = QtWidgets.QVBoxLayout(self.page_2)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.verticalLayout_8 = QtWidgets.QVBoxLayout(self.page_3)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.horizontalLayout_7 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")

    def _create_labels(self, dialog_instance) -> None:
        self.label = QtWidgets.QLabel(dialog_instance)
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(dialog_instance)
        self.label_2.setObjectName("label_2")
        self.label_3 = QtWidgets.QLabel(dialog_instance)
        self.label_3.setText("WHERE")
        self.label_3.setObjectName("label_3")
        self.label_4 = QtWidgets.QLabel(dialog_instance)
        self.label_4.setText("GROUP BY")
        self.label_4.setObjectName("label_4")
        self.label_5 = QtWidgets.QLabel(dialog_instance)
        self.label_5.setText("ORDER BY")
        self.label_5.setObjectName("label_5")

    def _create_textedits(self, dialog_instance) -> None:
        self.col = QtWidgets.QTextEdit(dialog_instance)
        self.col.setAcceptRichText(False)
        self.col.setMinimumSize(QtCore.QSize(400, 0))
        self.col.setObjectName("col")
        self.where = QtWidgets.QTextEdit(dialog_instance)
        self.where.setAcceptRichText(False)
        self.where.setObjectName("where")
        self.group = QtWidgets.QTextEdit(dialog_instance)
        self.group.setAcceptRichText(False)
        self.order = QtWidgets.QTextEdit(dialog_instance)
        self.order.setAcceptRichText(False)

    def _create_comboboxes(self) -> None:
        self.tables = QtWidgets.QComboBox(self.page)
        self.tables.setObjectName("tables")
        self.tables.addItem("")
        self.columns = QtWidgets.QComboBox(self.page)
        self.columns.setObjectName("columns")
        self.columns.addItem("")
        self.aggregates = QtWidgets.QComboBox(self.page)
        self.aggregates.setObjectName("aggregates")
        self.aggregates.addItem("")
        self.functions = QtWidgets.QComboBox(self.page)
        self.functions.setObjectName("functions")
        self.functions.addItem("")
        self.math = QtWidgets.QComboBox(self.page)
        self.math.setObjectName("math")
        self.math.addItem("")
        self.stringfct = QtWidgets.QComboBox(self.page)
        self.stringfct.setObjectName("stringfct")
        self.stringfct.addItem("")
        self.operators = QtWidgets.QComboBox(self.page)
        self.operators.setObjectName("operators")
        self.operators.addItem("")
        self.columns_2 = QtWidgets.QComboBox(self.page_2)
        self.columns_2.setObjectName("columns_2")
        self.columns_2.addItem("")
        self.table_idx = QtWidgets.QComboBox(self.page_3)
        self.table_idx.setObjectName("table_idx")
        self.table_idx.addItem("")
        self.table_target = QtWidgets.QComboBox(self.page_3)
        self.table_target.setObjectName("table_target")
        self.table_target.addItem("")

    def _create_other_objects(self, dialog_instance) -> None:
        self.toolBox = QtWidgets.QToolBox(dialog_instance)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.toolBox.sizePolicy().hasHeightForWidth())
        self.toolBox.setSizePolicy(sizePolicy)
        self.toolBox.setMinimumSize(QtCore.QSize(250, 0))
        self.toolBox.setMaximumSize(QtCore.QSize(250, 16777215))
        self.toolBox.setObjectName("toolBox")
        self.tab = QtWidgets.QLineEdit(dialog_instance)
        self.tab.setFrame(True)
        self.tab.setObjectName("tab")
        self.page = QtWidgets.QWidget()
        self.page.setGeometry(QtCore.QRect(0, 0, 250, 291))
        self.page.setObjectName("page")
        self.checkBox = QtWidgets.QCheckBox(self.page)
        font = QtGui.QFont()
        font.setPointSize(8)
        font.setKerning(True)
        self.checkBox.setFont(font)
        self.checkBox.setObjectName("checkBox")
        self.spacerItem_1 = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding)
        self.spacerItem_2 = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding)
        self.spacerItem_3 = QtWidgets.QSpacerItem(
            40, 20, QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Minimum)
        self.page_2 = QtWidgets.QWidget()
        self.page_2.setGeometry(QtCore.QRect(0, 0, 154, 155))
        self.page_2.setObjectName("page_2")
        self.extract = QtWidgets.QCheckBox(self.page_2)
        self.extract.setObjectName("extract")
        self.values = QtWidgets.QListView(self.page_2)
        self.values.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.values.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.values.setProperty("showDropIndicator", False)
        self.values.setDragEnabled(False)
        self.values.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        self.values.setObjectName("values")
        self.page_3 = QtWidgets.QWidget()
        self.page_3.setGeometry(QtCore.QRect(0, 0, 223, 122))
        self.page_3.setObjectName("page_3")
        self.usertree = QtWidgets.QPushButton(self.page_3)
        self.usertree.setObjectName("usertree")
        self.reset = QtWidgets.QPushButton(dialog_instance)
        self.reset.setObjectName("reset")
        self.buttonBox = QtWidgets.QDialogButtonBox(dialog_instance)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(True)
        self.buttonBox.setObjectName("buttonBox")

    def _set_correct_widget_pos(self) -> None:
        self.formLayout.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.formLayout.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.col)
        self.formLayout.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.formLayout.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.tab)
        self.formLayout.setWidget(
            2, QtWidgets.QFormLayout.FieldRole, self.where)
        self.formLayout.setWidget(
            3, QtWidgets.QFormLayout.FieldRole, self.group)
        self.formLayout.setWidget(
            4, QtWidgets.QFormLayout.FieldRole, self.order)
        self.formLayout.setWidget(
            2, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.formLayout.setWidget(
            3, QtWidgets.QFormLayout.LabelRole, self.label_4)
        self.formLayout.setWidget(
            4, QtWidgets.QFormLayout.LabelRole, self.label_5)
        self.horizontalLayout_6.addLayout(self.formLayout)
        self.verticalLayout_5.addWidget(self.checkBox)
        self.verticalLayout_5.addWidget(self.tables)
        self.verticalLayout_5.addWidget(self.columns)
        self.verticalLayout_5.addItem(self.spacerItem_1)
        self.verticalLayout_5.addWidget(self.line_2)
        self.verticalLayout_5.addWidget(self.aggregates)
        self.verticalLayout_5.addWidget(self.helper_frame)
        self.verticalLayout_5.addWidget(self.math)
        self.verticalLayout_5.addWidget(self.stringfct)
        self.verticalLayout_5.addWidget(self.operators)
        self.helper_layout.addWidget(self.functions)
        self.helper_layout.addWidget(self.postgis_info_btn)
        self.helper_layout.setContentsMargins(0, 0, 0, 0)
        self.toolBox.addItem(self.page, "")
        self.verticalLayout_6.addWidget(self.columns_2)
        self.verticalLayout_6.addWidget(self.extract)
        self.verticalLayout_6.addWidget(self.values)
        self.toolBox.addItem(self.page_2, "")
        self.verticalLayout_8.addWidget(self.table_idx)
        self.verticalLayout_8.addWidget(self.table_target)
        self.verticalLayout_8.addWidget(self.usertree)
        self.verticalLayout_8.addItem(self.spacerItem_2)
        self.toolBox.addItem(self.page_3, "")
        self.verticalLayout_4.addWidget(self.toolBox)
        self.horizontalLayout_6.addLayout(self.verticalLayout_4)
        self.verticalLayout_7.addLayout(self.horizontalLayout_6)
        self.horizontalLayout_7.addWidget(self.reset)
        self.horizontalLayout_7.addItem(self.spacerItem_3)
        self.horizontalLayout_7.addWidget(self.buttonBox)
        self.verticalLayout_7.addLayout(self.horizontalLayout_7)
        self.toolBox.setCurrentIndex(0)

    def _create_postgis_helper(self) -> None:
        self.postgis_info_dialog = PostGISHelpDialog(self)
        self.postgis_info_btn = QtWidgets.QPushButton('ℹ️')
        self.postgis_info_btn.setToolTip(
            tr('Show information about PostGIS features.'))
        self.postgis_info_btn.clicked.connect(self.postgis_info_dialog.run)
        self.postgis_info_btn.setMaximumSize(22, 22)
        self.helper_layout = self.helper_frame.layout()

    def create_widgets(self, dialog_instance) -> None:
        self.postgis_info_dialog = PostGISHelpDialog(self)
        self._create_textedits(dialog_instance)
        self._create_labels(dialog_instance)
        self._create_other_objects(dialog_instance)
        self._create_layouts(dialog_instance)
        self._create_comboboxes()
        self._create_postgis_helper()
        self._set_correct_widget_pos()

    def setup_actions(self, dialog_instance) -> None:
        self.buttonBox.rejected.connect(dialog_instance.reject)
        self.buttonBox.accepted.connect(dialog_instance.accept)
        self.reset.clicked.connect(self.where.clear)
        self.reset.clicked.connect(self.tab.clear)
        self.reset.clicked.connect(self.col.clear)
        self.reset.clicked.connect(self.columns.clear)
        QtCore.QMetaObject.connectSlotsByName(dialog_instance)

    def retranslateUi(self, dialog_instance):
        _translate = QtCore.QCoreApplication.translate
        dialog_instance.setWindowTitle(
            _translate("CustomQueryBuilderDialog",
                       "PostGIS Toolbox - SQL Query Builder"))

        self.label.setText(
            _translate("CustomQueryBuilderDialog", "SELECT"))
        self.label_2.setText(
            _translate("CustomQueryBuilderDialog", "FROM"))
        self.reset.setText(
            _translate("CustomQueryBuilderDialog", "&Reset"))

        if QSettings().value('locale/userLocale')[0:2] == 'pl':
            self.tables.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Tabele"))
            self.checkBox.setText(
                _translate("DbManagerQueryBuilderDlg",
                           "Pokaż tabele systemowe"))
            self.columns.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Kolumny"))
            self.columns_2.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Kolumny"))
            self.aggregates.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Agregujące"))
            self.functions.setItemText(
                0, _translate("CustomQueryBuilderDialog",
                              "Przestrzenne (geometryczne)"))
            self.math.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Matematyczne"))
            self.stringfct.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Tekstowe"))
            self.operators.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Operatory"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page),
                _translate("CustomQueryBuilderDialog", "Dane"))
            self.extract.setText(
                _translate("CustomQueryBuilderDialog", "Pierwsze 10 wartości"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page_2),
                _translate("CustomQueryBuilderDialog", "Wartości kolumn"))
            self.table_idx.setItemText(
                0, _translate("CustomQueryBuilderDialog",
                              "Table (with spatial index)"))
            self.table_target.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Tabela (docelowa)"))
            self.usertree.setText(
                _translate("CustomQueryBuilderDialog",
                           "Użyj indeksu przestrzennego"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page_3),
                _translate("CustomQueryBuilderDialog", "Indeks przestrzenny"))

        else:
            self.checkBox.setText(
                _translate("CustomQueryBuilderDialog", "Show system tables"))
            self.tables.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Tables"))
            self.columns.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Columns"))
            self.aggregates.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Aggregates"))
            self.functions.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Functions"))
            self.math.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Math"))
            self.stringfct.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Strings functions"))
            self.operators.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Operators"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page),
                _translate("CustomQueryBuilderDialog", "Data"))
            self.columns_2.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Columns"))
            self.extract.setText(
                _translate("CustomQueryBuilderDialog", "Only 10 first values"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page_2),
                _translate("CustomQueryBuilderDialog", "Columns values"))
            self.table_idx.setItemText(
                0, _translate("CustomQueryBuilderDialog",
                              "Table (with spatial index)"))
            self.table_target.setItemText(
                0, _translate("CustomQueryBuilderDialog", "Table (Target)"))
            self.usertree.setText(
                _translate("CustomQueryBuilderDialog", "Use spatial index"))
            self.toolBox.setItemText(
                self.toolBox.indexOf(self.page_3),
                _translate("CustomQueryBuilderDialog", "Spatial index"))