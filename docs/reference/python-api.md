# Python API support policy

## 1. Stable canonical high-level API

The `panelsolver` package root exports only the first-release in-memory API:

```python
from panelsolver import (
    FMFCase,
    HypersonicCase,
    ResolvedAttitude,
    SolveResult,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
```

`FMFCase` and `HypersonicCase` are separate domain types with separate required
physical inputs. Both state their ordered STL paths, STL scale, reference area,
moment reference in STL axes, three reference lengths, and a
`ResolvedAttitude`. `FMFCase` uses resolved Sentman Mode A inputs (`speed_ratio`,
translational temperature, and wall temperature); atmosphere-based Mode B
resolution remains available through the lower-level model API.

`solve_fmf()` and `solve_hypersonic()` call the existing shared numerical
pipeline. They do not create Summary CSV, VTP, PNG, temporary output directories,
or any other filesystem artifact. `SolveResult.coefficients` exposes integrated
coefficients; components, geometry, shielding state, per-face traction and model
scalars remain available on the same in-memory result. Filesystem-producing
batch work is an explicit CLI operation, not a side effect of these functions.

Both case types apply the same portable `case_id` contract as the case-table
reader: Unicode NFC normalization; non-empty text after normalization; rejection
of `.`, `..`, path separators, control characters, Windows-invalid characters,
Windows reserved names, and trailing dots or spaces. NFC-equivalent IDs therefore
produce the same canonical signature identity when all other inputs match.

`resolve_attitude()` accepts `None` or text for `attitude_input`; `None` and blank
text select `beta_tan`, and valid text is case-insensitive. Non-text selectors are
rejected. The supported angle domains are `abs(alpha_deg) < 90` and
`abs(beta_or_bank_deg) < 90` for `beta_tan`; `abs(alpha_deg) < 90` with any finite
second angle for `beta_sin`; and finite included angle plus finite periodic bank
angle for `bank`.

## 2. Lower-level architecture API

`panelsolver.core`, `panelsolver.models`, and `panelsolver.app` expose typed
contracts and composition functions used by the applications. They are useful
for development and advanced integrations, and the central load-vector contract
is recorded in [ADR 0002](../adr/0002-panel-load-vector-contract.md). They remain
lower-level architecture surfaces: callers must construct validated geometry,
flow, model, signature, and execution policy objects explicitly.

These modules are not re-exported wholesale from the package root.

## 3. Legacy package imports are unsupported

`fmfsolver.*` and `newtsolver.*` direct-Python APIs have been removed. Those
package names remain in the distribution only because the six legacy console
commands use small internal frontends. Their modules, attributes, functions,
classes, and version names are not public APIs and may change without
deprecation.

Migrate integrations to the stable package-root API above. Use the canonical or
legacy commands for case-table execution and artifact generation. The supported
case-file and output contracts are documented in [Compatibility](compatibility.md).
This transition is recorded in
[ADR 0014](../adr/0014-remove-legacy-direct-python-api.md).

## 4. Private compatibility implementation

`panelsolver._compat` retains only internal legacy artifact-signature
reconstruction and its historical version inputs. This package and the private
legacy command frontends are not public APIs.

The package-root API above is the stable canonical high-level API;
`panelsolver.core`, `panelsolver.models`, and `panelsolver.app` are lower-level
architecture APIs; and the legacy command plumbing is private implementation.

## Test-policy classification

- Release contracts are covered by command, normal GUI, case-table,
  Summary CSV/VTP, installed-wheel, and supported numerical regression tests.
- Installed-wheel tests reject removed legacy direct-Python modules and verify
  that the legacy packages contain only command and GUI compatibility plumbing.
- Phase 1 fixtures/goldens and Phase 3 adapter regressions are historical
  evidence and remain read-only inputs to compatibility decisions.
