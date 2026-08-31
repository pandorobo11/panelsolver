# Python API support policy

## Stable package-root API

The supported in-memory API is exported from the `panelsolver` package root:

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

`FMFCase` and `HypersonicCase` are separate domain types with separate physical
inputs. Both specify ordered STL paths, STL scale, reference area, the moment
reference in STL axes, three reference lengths, and a `ResolvedAttitude`.
`FMFCase` accepts resolved Sentman inputs: speed ratio, incident translational
temperature, and wall temperature. Atmosphere-derived FMF Mode B is available
through the documented case-table interface used by the CLI and GUI; it is not
an alternative constructor mode of the package-root `FMFCase`.

`resolve_attitude()` converts the documented `beta_tan`, `beta_sin`, or `bank`
input into a `ResolvedAttitude`. `None` and blank text select `beta_tan`, and
valid text is case-insensitive. The angle domains are the same as those in
[Case files](../user-guide/case-files.md).

`solve_fmf()` accepts an `FMFCase`, and `solve_hypersonic()` accepts a
`HypersonicCase`. Both return a `SolveResult`. Its coefficients, component
results, geometry, shielding state, per-face traction, and model visualization
scalars remain in memory.

## Filesystem boundary

The package-root solve functions do not create Summary CSV, VTP, PNG, temporary
output directories, or other filesystem artifacts. Use the documented CLI or
GUI case-table workflow when file outputs or atmosphere-derived FMF Mode B
resolution are required.

Both case types apply the portable `case_id` rules documented in
[Case files](../user-guide/case-files.md). Equivalent Unicode NFC identifiers
therefore produce the same canonical signature identity when all other inputs
match.

No other Python package identity is distributed. Use the package-root API above,
or a documented command for case-table execution and artifact generation. The
supported product surface is summarized in [Compatibility](compatibility.md).
