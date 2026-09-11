# GUI tests

Shared GUI, viewer, case selection, and lifecycle tests belong here. They use
injected non-OpenGL plotters and deterministic execution adapters so they remain
separable from headless numerical tests and run on every CI platform.

Run-lifecycle fixtures register each panel and window with `own_widget` as soon
as it is constructed, including widgets created in subtests. Unittest cleanup
retains them, cancels and waits for any active run, closes the widget, and deletes
its native Qt tree on the GUI thread. Closing alone only hides a widget; leaving
its destruction to Python cyclic GC can let a later worker collect GUI wrappers
and clear Python layout state before Qt finishes using it (issue #297).

`test_gui_fixture_lifecycle.py` runs each lifecycle case once in a bounded subprocess,
forces GC in the real Qt worker, and checks native destruction after every test,
including an intentional test failure during a run. This also checks direct
unittest cleanup rather than relying on pytest teardown. GC stays enabled.
The normal launcher retains its MainWindow throughout the event loop, and the
window owns both panels; this fixture fix does not change application ownership
or the separate native accessibility limitation tracked in issue #284.

The pinned GUI-visible legacy behavior and known product differences are
inventoried in `devdocs/history/migration/phase1/BEHAVIORAL_INVENTORY.md` and
`devdocs/history/migration/phase1/LEGACY_DIFFERENCES.md`. Platform-dependent screenshots are not Phase
1 goldens.
