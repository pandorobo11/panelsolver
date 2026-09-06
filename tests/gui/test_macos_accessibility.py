"""Exercise Cocoa table ownership in an isolated normal-display process."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest

# QTBUG-149612 / Qt change 765434: resolving a selected cell after creating
# native row placeholders can delete the parent table interface. A regular
# QAccessible-only or offscreen test never enters the faulty Cocoa code.
_NATIVE_TABLE_PROBE = r"""
import ctypes

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.app.gui_components import FrozenCaseTable

application = QtWidgets.QApplication([])
assert application.platformName() == "cocoa"
objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
objc.objc_getClass.argtypes = [ctypes.c_char_p]
objc.objc_getClass.restype = ctypes.c_void_p
objc.sel_registerName.argtypes = [ctypes.c_char_p]
objc.sel_registerName.restype = ctypes.c_void_p


def send(receiver, selector, result=ctypes.c_void_p, arguments=(), types=()):
    signature = ctypes.CFUNCTYPE(
        result, ctypes.c_void_p, ctypes.c_void_p, *types
    )
    method = signature(("objc_msgSend", objc))
    return method(
        receiver, objc.sel_registerName(selector.encode()), *arguments
    )


def items(array):
    count = send(array, "count", ctypes.c_ulong)
    return [
        send(array, "objectAtIndex:", arguments=(i,), types=(ctypes.c_ulong,))
        for i in range(count)
    ]


for factory in (QtWidgets.QTableWidget, FrozenCaseTable):
    table = factory()
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.resize(600, 400)
    table.show()
    application.processEvents()
    element_class = objc.objc_getClass(b"QMacAccessibilityElement")
    assert element_class, "Qt Cocoa accessibility class was not loaded"
    for columns in (2, 3, 2):
        table.setColumnCount(columns)
        table.setRowCount(3)
        for row in range(3):
            for column in range(columns):
                table.setItem(row, column, QtWidgets.QTableWidgetItem(
                    f"case-{row}-value-{column}"
                ))
        if isinstance(table, FrozenCaseTable):
            table.refresh_frozen()
        application.processEvents()
        views = (table, table.frozen) if isinstance(table, FrozenCaseTable) else (table,)
        for view in views:
            interface = QtGui.QAccessible.queryAccessibleInterface(view)
            table_id = QtGui.QAccessible.uniqueId(interface)
            native = send(element_class, "elementWithId:",
                          arguments=(table_id,), types=(ctypes.c_uint,))
            assert native
            # Populate the parent-managed row/cell placeholders first.
            for row in items(send(native, "accessibilityRows")):
                assert items(send(row, "accessibilityChildren"))
            for row_index in range(3):
                table.selectRow(row_index)
                application.processEvents()
                selected = items(send(native, "accessibilitySelectedChildren"))
                assert QtGui.QAccessible.accessibleInterface(table_id) is not None
                assert selected, "Selected cells must remain exposed"
                if view is table:
                    assert len(selected) == columns
                for child in selected:
                    role = send(child, "accessibilityRole")
                    assert send(role, "UTF8String", ctypes.c_char_p) == b"AXCell"
    table.close()
    application.processEvents()
print("Cocoa selected cells and parent table IDs survived all model/selection cycles")
"""


@unittest.skipUnless(sys.platform == "darwin", "requires the macOS Cocoa bridge")
class MacAccessibilityTests(unittest.TestCase):
    def test_native_selected_cells_preserve_table_interfaces(self) -> None:
        environment = dict(os.environ)
        # Other GUI tests use offscreen stubs in the parent process. This
        # subprocess must exercise real Cocoa, without changing their setup.
        environment["QT_QPA_PLATFORM"] = "cocoa"
        environment.pop("PYVISTA_OFF_SCREEN", None)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(_NATIVE_TABLE_PROBE)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
