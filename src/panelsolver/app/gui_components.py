"""Small Qt-native workbench components; no domain or execution policy."""

from PySide6 import QtCore, QtWidgets


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


class FlowLayout(QtWidgets.QLayout):
    """Wrap complete control groups without hiding commands at narrow widths."""

    def __init__(self, parent=None, *, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
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
                if apply:
                    item.setGeometry(QtCore.QRect(x, y, size.width(), size.height()))
                x += size.width() + self.spacing()
                height = max(height, size.height())
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
