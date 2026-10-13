"""Small Qt-native workbench components; no domain or execution policy."""

from PySide6 import QtCore, QtGui, QtWidgets


class WorkbenchSpinBox(QtWidgets.QSpinBox):
    """Keep the native editor with the same content height as themed buttons."""

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(max(20, self.fontMetrics().height()) + 10)
        return size

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setHeight(self.sizeHint().height())
        return size


class ElidedPathField(QtWidgets.QLineEdit):
    """Read-only path display that keeps the file name and nearest folders.

    When the path is too wide, leading folders are replaced by an ellipsis.
    ``text()`` and the tooltip keep the full path; only the painted text is
    shortened to the current width.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setReadOnly(True)
        # A read-only field must not swallow file drops meant for the window.
        self.setAcceptDrops(False)

    def text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:
        self._full_text = str(text)
        self.setToolTip(self._full_text)
        self.setAccessibleDescription(self._full_text)
        self._apply_elision()

    def clear(self) -> None:
        self.setText("")

    def displayed_text(self) -> str:
        return super().text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.Type.FontChange,
            QtCore.QEvent.Type.StyleChange,
        ):
            self._apply_elision()

    def keyPressEvent(self, event) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Copy):
            self._copy_full_text()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QtWidgets.QMenu(self)
        action = menu.addAction("Copy Path")
        action.setEnabled(bool(self._full_text))
        action.triggered.connect(self._copy_full_text)
        menu.exec(event.globalPos())

    def _copy_full_text(self) -> None:
        if self._full_text:
            QtWidgets.QApplication.clipboard().setText(self._full_text)

    def _available_text_width(self) -> int:
        option = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(option)
        contents = self.style().subElementRect(
            QtWidgets.QStyle.SubElement.SE_LineEditContents, option, self
        )
        margins = self.textMargins()
        # QLineEdit keeps a fixed 2px horizontal text margin on each side.
        return max(0, contents.width() - margins.left() - margins.right() - 4)

    def _elided_text(self, width: int) -> str:
        metrics = self.fontMetrics()
        text = self._full_text
        if metrics.horizontalAdvance(text) <= width:
            return text
        split = max(text.rfind("/"), text.rfind("\\")) + 1
        folder, name = text[:split], text[split:]
        folder_width = width - metrics.horizontalAdvance(name)
        if folder and folder_width > metrics.horizontalAdvance("…"):
            return (
                metrics.elidedText(
                    folder, QtCore.Qt.TextElideMode.ElideLeft, folder_width
                )
                + name
            )
        return metrics.elidedText(text, QtCore.Qt.TextElideMode.ElideMiddle, width)

    def _apply_elision(self) -> None:
        super().setText(self._elided_text(self._available_text_width()))
        self.setCursorPosition(0)


class FittedComboBox(QtWidgets.QComboBox):
    """Combo box whose width reserves the longest of a known set of texts.

    Selecting a different item then neither clips its text nor reflows the
    surrounding controls.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._reserved_texts: tuple[str, ...] = ()

    def set_reserved_texts(self, texts) -> None:
        self._reserved_texts = tuple(str(text) for text in texts)
        self.updateGeometry()

    def _with_reserved_width(self, size: QtCore.QSize) -> QtCore.QSize:
        if not self._reserved_texts:
            return size
        metrics = self.fontMetrics()
        width = max(metrics.horizontalAdvance(text) for text in self._reserved_texts)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        reserved = self.style().sizeFromContents(
            QtWidgets.QStyle.ContentsType.CT_ComboBox,
            option,
            QtCore.QSize(width, metrics.height()),
            self,
        )
        return QtCore.QSize(max(size.width(), reserved.width()), size.height())

    def sizeHint(self) -> QtCore.QSize:
        return self._with_reserved_width(super().sizeHint())

    def minimumSizeHint(self) -> QtCore.QSize:
        return self._with_reserved_width(super().minimumSizeHint())


class _GripSplitterHandle(QtWidgets.QSplitterHandle):
    """Paint a visible divider and grip so the pane boundary reads as movable."""

    def __init__(self, orientation, parent) -> None:
        super().__init__(orientation, parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)

    def event(self, event) -> bool:
        if event.type() in (
            QtCore.QEvent.Type.HoverEnter,
            QtCore.QEvent.Type.HoverLeave,
        ):
            self.update()
        return super().event(event)

    def paintEvent(self, _event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        role = QtGui.QPalette.ColorRole
        horizontal = self.orientation() == QtCore.Qt.Orientation.Horizontal
        rect = self.rect()
        divider = QtCore.QRectF(rect)
        if horizontal:
            divider.setLeft(rect.center().x())
            divider.setWidth(1)
        else:
            divider.setTop(rect.center().y())
            divider.setHeight(1)
        painter.fillRect(divider, palette.color(role.Midlight))
        if self.underMouse():
            grip_color = palette.color(role.Highlight)
        else:
            grip_color = QtGui.QColor(palette.color(role.Dark))
            grip_color.setAlphaF(0.45)
        length, thickness = 40, 4
        if horizontal:
            grip = QtCore.QRectF(0, 0, thickness, length)
        else:
            grip = QtCore.QRectF(0, 0, length, thickness)
        grip.moveCenter(QtCore.QRectF(rect).center())
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(grip_color)
        painter.drawRoundedRect(grip, thickness / 2, thickness / 2)


class WorkbenchSplitter(QtWidgets.QSplitter):
    """Splitter whose handle shows a divider and a grip in both themes."""

    def __init__(self, orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(9)

    def createHandle(self) -> QtWidgets.QSplitterHandle:
        return _GripSplitterHandle(self.orientation(), self)


class FlowLayout(QtWidgets.QLayout):
    """Wrap complete control groups without hiding commands at narrow widths."""

    def __init__(self, parent=None, *, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        widget = item.widget()
        if widget is not None:
            # Native styles can inset layout-item rects (macOS buttons by
            # 12px vertically). Flow rows must reserve the whole widget rect
            # so controls cannot paint outside their parent or wrapped line.
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
        self._items.append(item)

    def addLayout(self, layout) -> None:
        self.addChildLayout(layout)
        self.addItem(layout)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        items = [item for item in self._items if not item.isEmpty()]
        margins = self.contentsMargins()
        return QtCore.QSize(
            sum(item.sizeHint().width() for item in items)
            + max(0, len(items) - 1) * self.spacing()
            + margins.left()
            + margins.right(),
            max((item.sizeHint().height() for item in items), default=0)
            + margins.top()
            + margins.bottom(),
        )

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QtCore.QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _arrange(self, rect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        y = area.y()
        line = []
        line_width = 0

        def place_line():
            x = area.x()
            expanding = [
                item
                for item, _size in line
                if item.expandingDirections() & QtCore.Qt.Orientation.Horizontal
            ]
            spare = max(0, area.width() - line_width)
            height = 0
            for item, size in line:
                if item in expanding:
                    extra = spare // len(expanding)
                    size.setWidth(size.width() + extra)
                    spare -= extra
                    expanding.remove(item)
                if item.hasHeightForWidth():
                    size.setHeight(item.heightForWidth(size.width()))
                height = max(height, size.height())
            for item, size in line:
                if apply:
                    item.setGeometry(
                        QtCore.QRect(
                            x,
                            y + (height - size.height()) // 2,
                            size.width(),
                            size.height(),
                        )
                    )
                x += size.width() + self.spacing()
            return height

        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            # A group's preferred single-row width may exceed the available
            # space. Let its layout shrink/wrap within its real minimum width.
            size.setWidth(
                max(item.minimumSize().width(), min(size.width(), area.width()))
            )
            if line and line_width + self.spacing() + size.width() > area.width():
                y += place_line() + self.spacing()
                line = []
                line_width = 0
            line_width += (self.spacing() if line else 0) + size.width()
            line.append((item, size))
        return y + place_line() - rect.y() + margins.bottom()


class _PinnedDelegate(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        if self.parent().hasFocus():
            option.state |= QtWidgets.QStyle.StateFlag.State_Active
        else:
            option.state &= ~QtWidgets.QStyle.StateFlag.State_Active


class FrozenCaseTable(QtWidgets.QTableWidget):
    """One case model and selection with a pinned first-column view."""

    def __init__(self) -> None:
        super().__init__()
        self.frozen = QtWidgets.QTableView(self)
        self.frozen.setProperty("workbenchPinned", True)
        for table in (self, self.frozen):
            table.setProperty("workbenchCases", True)
            table.setShowGrid(False)
        self.frozen.setModel(self.model())
        self.frozen.setItemDelegate(_PinnedDelegate(self))
        self.frozen.setSelectionModel(self.selectionModel())
        self.frozen.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.frozen.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.frozen.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.frozen.setFocusProxy(self)
        self.frozen.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.frozen.setAlternatingRowColors(True)
        self.frozen.verticalHeader().hide()
        self.frozen.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.frozen.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setHorizontalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.frozen.setVerticalScrollMode(self.verticalScrollMode())
        self.frozen.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frozen.setAccessibleName("Pinned Case ID")
        self.horizontalHeader().sectionResized.connect(self._sync_width)
        self.frozen.horizontalHeader().sectionResized.connect(self._resize_pinned)
        self.verticalHeader().sectionResized.connect(
            lambda row, _old, size: self.frozen.setRowHeight(row, size)
        )
        self.verticalScrollBar().valueChanged.connect(
            self.frozen.verticalScrollBar().setValue
        )
        self.frozen.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue
        )
        self.model().modelReset.connect(self.refresh_frozen)
        self.model().columnsInserted.connect(self.refresh_frozen)
        self.model().columnsRemoved.connect(self.refresh_frozen)
        self.frozen.hide()

    def _resize_pinned(self, column: int, _old: int, size: int) -> None:
        if column == 0:
            self.setColumnWidth(0, size)

    def _sync_width(self, column: int, _old: int, size: int) -> None:
        if column == 0:
            self.frozen.setColumnWidth(0, size)
            self._place_frozen()

    def refresh_frozen(self, *_args) -> None:
        for column in range(self.columnCount()):
            self.frozen.setColumnHidden(column, column != 0)
        for row in range(self.rowCount()):
            self.frozen.setRowHeight(row, self.rowHeight(row))
        self.frozen.setVisible(self.columnCount() > 0)
        self.frozen.setColumnWidth(0, self.columnWidth(0))
        self._place_frozen()

    def _place_frozen(self) -> None:
        self.frozen.horizontalHeader().setFixedHeight(self.horizontalHeader().height())
        viewport = self.viewport().geometry()
        self.frozen.setGeometry(
            viewport.x(),
            self.frameWidth(),
            self.columnWidth(0),
            viewport.height() + self.horizontalHeader().height(),
        )
        self.frozen.raise_()
        # macOS can draw a transient horizontal scrollbar over the viewport.
        self.horizontalScrollBar().parentWidget().raise_()

    def updateGeometries(self) -> None:
        super().updateGeometries()
        if hasattr(self, "frozen"):
            self._place_frozen()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.frozen.viewport().update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.frozen.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_frozen()

    def scrollTo(
        self, index, hint=QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible
    ) -> None:
        if index.column() == 0:
            vertical = self.horizontalScrollBar().value()
            super().scrollTo(index, hint)
            self.horizontalScrollBar().setValue(vertical)
        else:
            super().scrollTo(index, hint)
            rect = self.visualRect(index)
            if rect.left() < self.columnWidth(0):
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() + rect.left() - self.columnWidth(0))
