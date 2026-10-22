"""Keep native fixture lifetime failures isolated from the pytest process."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.slow
def test_run_fixtures_are_destroyed_before_worker_gc():
    probe = r"""
import gc
import threading
import unittest
from unittest.mock import patch

from tests.gui import test_run_lifecycle as lifecycle

gui_thread = threading.get_ident()
created = []
destroyed = []
gc_threads = []

def watch(original):
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        token = len(created)
        created.append(token)
        # Capture only a token, never the widget whose lifetime we measure.
        self.destroyed.connect(
            lambda: destroyed.append((token, threading.get_ident()))
        )
    return initialize

original_adapters = lifecycle._adapters

def adapters(rows, runner):
    def collect_and_run(request):
        gc_threads.append(threading.get_ident())
        gc.collect()
        return runner(request)
    return original_adapters(rows, collect_and_run)

def assert_destroyed():
    assert sorted(token for token, _ in destroyed) == created, (
        'test left native GUI fixtures alive', created, destroyed
    )
    assert all(thread == gui_thread for _, thread in destroyed)
    assert gc.isenabled()

class InterruptedTest(lifecycle.RunLifecycleTests):
    def fail_during_run(self):
        def runner(request):
            while not request.cancel_requested():
                threading.Event().wait(0.001)
            raise lifecycle.SchedulerCancelled('cleanup cancellation')
        panel, rows, _ = self.make_panel(runner)
        window = self.own_widget(lifecycle.MainWindow(
            panel.spec, cases_panel=panel, viewer_panel=lifecycle._FakeViewer()
        ))
        window.show()
        assert panel.start_run(rows, 1, 0, 'results.csv')
        self.fail('intentional failure while worker is active')

with (
    patch.object(lifecycle.CasesPanel, '__init__',
                 watch(lifecycle.CasesPanel.__init__)),
    patch.object(lifecycle.MainWindow, '__init__',
                 watch(lifecycle.MainWindow.__init__)),
    patch.object(lifecycle, '_adapters', adapters),
):
    lifecycle.RunLifecycleTests.setUpClass()
    names = unittest.defaultTestLoader.getTestCaseNames(lifecycle.RunLifecycleTests)
    for name in names:
        result = unittest.TestResult()
        lifecycle.RunLifecycleTests(name).run(result)
        assert result.wasSuccessful(), (result.errors, result.failures)
        assert_destroyed()

    result = unittest.TestResult()
    InterruptedTest('fail_during_run').run(result)
    assert len(result.failures) == 1, result.failures
    assert 'intentional failure' in result.failures[0][1]
    assert not result.errors, result.errors
    assert_destroyed()

assert gc_threads and all(thread != gui_thread for thread in gc_threads)
print('GUI fixtures destroyed on the GUI thread; worker GC and failure cleanup passed')
"""
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", textwrap.dedent(probe)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "worker GC and failure cleanup passed" in result.stdout


@pytest.mark.slow
def test_cases_panel_fixtures_are_destroyed_after_each_test():
    probe = r"""
import threading
import unittest
from unittest.mock import patch

from panelsolver.app.main_window import MainWindow
from tests.gui import test_cases_panel as cases
from tests.gui import test_workbench as workbench
from tests.gui import test_workbench_usability as usability

gui_thread = threading.get_ident()
created = []
destroyed = []

def watch(original):
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        token = len(created)
        created.append(token)
        # Capture only a token, never the widget whose lifetime we measure.
        self.destroyed.connect(
            lambda: destroyed.append((token, threading.get_ident()))
        )
    return initialize

with (
    patch.object(cases.CasesPanel, '__init__', watch(cases.CasesPanel.__init__)),
    patch.object(MainWindow, '__init__', watch(MainWindow.__init__)),
):
    for case in (
        cases.CasesPanelTests,
        workbench.WorkbenchTests,
        usability.WorkbenchUsabilityTests,
    ):
        case.setUpClass()
        names = unittest.defaultTestLoader.getTestCaseNames(case)
        for name in names:
            result = unittest.TestResult()
            case(name).run(result)
            assert result.wasSuccessful(), (name, result.errors, result.failures)
            # A panel left to cyclic GC could be collected later by a Qt worker.
            assert sorted(token for token, _ in destroyed) == created, (
                name, 'test left a native CasesPanel or MainWindow alive',
                created, destroyed,
            )
            assert all(thread == gui_thread for _, thread in destroyed)

assert created
print('CasesPanel fixtures destroyed on the GUI thread after each test')
"""
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", textwrap.dedent(probe)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "destroyed on the GUI thread after each test" in result.stdout
