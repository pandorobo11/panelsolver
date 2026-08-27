"""Shared GUI shell with a common cooperative close lifecycle."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.docs_site import DocumentationSite

from .cases_panel import CasesPanel
from .examples import ExampleDefinition, ExampleLibrary
from .solver_spec import SolverSpec
from .versioning import panelsolver_distribution_version
from .viewer import ViewerPanel


class MainWindow(QtWidgets.QMainWindow):
    """Wire shared cases and viewer panels with common lifecycle behavior."""

    def __init__(
        self,
        spec: SolverSpec,
        *,
        cases_panel: QtWidgets.QWidget | None = None,
        viewer_panel: QtWidgets.QWidget | None = None,
        documentation_site: DocumentationSite | None = None,
        example_library: ExampleLibrary | None = None,
    ) -> None:
        if not isinstance(spec, SolverSpec):
            raise TypeError("spec must be a SolverSpec")
        super().__init__()
        self.spec = spec
        self._documentation_site = documentation_site or DocumentationSite()
        self._example_library = example_library or ExampleLibrary()
        self.setWindowTitle(spec.window_title)
        self.resize(1480, 900)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        self.cases_panel = cases_panel or CasesPanel(spec)
        self.viewer_panel = viewer_panel or ViewerPanel(spec)
        self.splitter.addWidget(self.cases_panel)
        self.splitter.addWidget(self.viewer_panel)
        self.splitter.setStretchFactor(1, 4)
        self._close_when_run_finishes = False
        self._build_file_menu()
        self._build_help_menu()

        self.viewer_panel.log_message.connect(self.cases_panel.logln)
        self.cases_panel.vtp_loaded.connect(self.viewer_panel.load_vtp)
        self.cases_panel.vtp_artifact_invalidated.connect(
            self.viewer_panel.invalidate_vtp_artifact
        )
        self.cases_panel.viewer_clear_requested.connect(self.viewer_panel.clear_view)
        self.cases_panel.cases_updated.connect(self.viewer_panel.set_case_rows)
        self.cases_panel.selected_cases_changed.connect(
            self.viewer_panel.set_selected_case_rows
        )
        self.cases_panel.input_path_changed.connect(self.viewer_panel.set_input_path)
        self.cases_panel.run_finished.connect(self._on_case_run_finished)
        self.viewer_panel.save_selected_images_requested.connect(
            self._on_save_selected_images
        )

    def _build_file_menu(self) -> None:
        self.file_menu = self.menuBar().addMenu("File")
        self.open_input_action = QtGui.QAction("Open Input File...", self)
        self.open_input_action.triggered.connect(self.cases_panel.pick_input_file)
        self.file_menu.addAction(self.open_input_action)

        self.new_from_example_menu = self.file_menu.addMenu("New from Example")
        self.example_actions: tuple[QtGui.QAction, ...] = tuple(
            self._add_example_action(example) for example in self.spec.examples
        )
        self.new_from_example_menu.setEnabled(bool(self.example_actions))

        self.file_menu.addSeparator()
        self.exit_action = QtGui.QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

    def _add_example_action(self, example: ExampleDefinition) -> QtGui.QAction:
        action = QtGui.QAction(example.label, self)
        action.setData(example.input_resource)
        action.triggered.connect(
            lambda _checked=False, selected=example: self._new_from_example(selected)
        )
        self.new_from_example_menu.addAction(action)
        return action

    def _new_from_example(self, example: ExampleDefinition) -> None:
        if self.cases_panel.is_running():
            self.cases_panel.logln(
                "[WARN] Cannot create an example while cases are running."
            )
            return
        destination = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            f"Select Workspace for {example.label} Example",
            str(Path.cwd()),
        )
        if not destination:
            return
        try:
            input_path = self._example_library.copy_example(example, destination)
        except Exception as exc:
            self.cases_panel.logln(f"[ERROR] Failed to copy example: {exc}")
            QtWidgets.QMessageBox.critical(
                self,
                "Example Copy Error",
                str(exc),
            )
            return
        self.cases_panel.logln(f"[OK] Copied example workspace: {destination}")
        self.cases_panel.load_input_file(
            input_path,
            remember_directory=False,
        )

    def _build_help_menu(self) -> None:
        self.help_menu = self.menuBar().addMenu("Help")
        self.documentation_action = QtGui.QAction("Documentation", self)
        self.documentation_action.triggered.connect(
            lambda: self._open_documentation("index.html")
        )
        self.help_menu.addAction(self.documentation_action)
        self.help_menu.addSeparator()

        self.about_action = QtGui.QAction("About", self)
        self.about_action.triggered.connect(self._show_about)
        self.help_menu.addAction(self.about_action)

    def _open_documentation(self, page: str) -> None:
        try:
            target = self._documentation_site.resolve(page)
            opened = QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(target))
            )
            if not opened:
                raise RuntimeError(
                    "The default browser did not accept the local documentation URL."
                )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Panel Solver documentation error",
                str(exc),
            )

    @QtCore.Slot()
    def _show_about(self) -> None:
        try:
            version = panelsolver_distribution_version()
        except PackageNotFoundError:
            version = "not installed"
        QtWidgets.QMessageBox.about(
            self,
            "About Panel Solver",
            "\n".join(
                (
                    "Panel Solver",
                    f"version {version}",
                    f"Domain: {self.spec.domain_name}",
                    "License: Apache-2.0",
                )
            ),
        )

    @QtCore.Slot()
    def _on_save_selected_images(self) -> None:
        rows = self.cases_panel.selected_case_rows()
        if not rows:
            self.cases_panel.logln(
                "[WARN] Select at least one case to batch-save images."
            )
            return
        self.viewer_panel.save_images_for_case_rows(rows)

    def closeEvent(self, event) -> None:
        """Cancel an active run and defer close until its thread is cleaned up."""
        if self.cases_panel.is_running():
            if not self._close_when_run_finishes:
                self._close_when_run_finishes = True
                self.cases_panel.cancel_run()
                self.cases_panel.logln("[CLOSE] Waiting for the active run to stop...")
            event.ignore()
            return
        self._documentation_site.close()
        super().closeEvent(event)

    @QtCore.Slot()
    def _on_case_run_finished(self) -> None:
        if self._close_when_run_finishes:
            self._close_when_run_finishes = False
            QtCore.QTimer.singleShot(0, self.close)


__all__ = ("MainWindow",)
