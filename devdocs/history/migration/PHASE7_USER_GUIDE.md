# Phase 7 user, release, and rollback guide

Historical record — non-normative. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present contract.

Phase 7 provides one `panel-solvers` distribution containing the shared engine,
both physical models, both compatibility packages, and all six old command
names. It does not deprecate the old names or perform the Phase 8 audit.

Phase 8 is complete. ADR 0008 limits the accepted compatibility surface to
commands, normal launcher-driven GUI operation, documented case files, and
documented result semantics. Direct Python details below describe the current
implementation on a best-effort basis rather than a frozen product contract.
The final evidence is in `../audits/PHASE8_EXECUTION_RECORD.md` and
`../audits/PHASE8_FINAL_AUDIT.md`.

## Install or migrate

Python 3.12 or newer is required. The new wheel and either legacy distribution
must not coexist because they provide overlapping `fmfsolver`/`newtsolver`
packages and commands.

```bash
python -m pip uninstall fmfsolver newtsolver panel-solvers
python -m pip install panel_solvers-<version>-py3-none-any.whl
```

Install the platform's `rayaccel` extra when installing from a source/index that
exposes extras. A forced `embree` case remains an error if Embree is unavailable;
it never silently falls back. `rtree` remains supported.

One distribution version and two compatibility versions are intentional:

- `importlib.metadata.version("panel-solvers")` returns `0.1.0`;
- `fmfsolver.__version__` returns the frozen FMF value `1.3.8`;
- `newtsolver.__version__` returns the frozen newtsolver value `1.0.3`.

## Commands

`fmfsolver` and `fmfsolver-gui` open `Sentman FMF Solver (GUI)`;
`newtsolver` and `newtsolver-gui` open `newtsolver (GUI)`. Batch use is:

```bash
fmfsolver-cli --input cases.csv --output results.csv --workers 1
newtsolver-cli --input cases.csv --output results.csv --workers 1
```

Both CLIs accept `--cases` with space- or comma-separated case IDs and
`--flush-every-cases N` for complete input-ordered checkpoint snapshots. Zero
disables checkpoints; the default is 100. If `--output` is omitted, the result
is `<input_dir>/outputs/<input_stem>_result.csv`. Omitting `--cases` runs every
case. Supplying `--cases` without a value is an argument error for both products.

## Input

CSV, XLSX, XLSM, and legacy BIFF XLS are accepted by both products. OOXML files
use openpyxl and BIFF files use xlrd. Paths in `stl_path` and `out_dir` are
resolved relative to the input table. Semicolons preserve ordered multi-component
STL and newtsolver equation lists. The committed unchanged examples
are `tests/fixtures/phase1/inputs/fmfsolver_cases.csv` and
`tests/fixtures/phase1/inputs/newtsolver_cases.csv`.

Common required fields are `case_id`, `stl_path`, `stl_scale_m_per_unit`,
attitude angles, the three reference coordinates, `Aref_m2`, and three reference
lengths. FMF additionally selects either Mode A (`S` and `Ti_K`) or Mode B
(`Mach` and `Altitude_km`) and requires `Tw_K`. newtsolver requires `Mach` and
`gamma` and accepts independent windward/leeward equations. The exact ordered
schemas, defaults, and validation rules are in the product `io/io_cases.py`
adapters and frozen by Phase 1 compatibility tests.

Case IDs use one portable filename rule for both products. Filesystem-safe
Unicode is accepted; empty IDs, path separators, control characters, Windows
reserved names, trailing dots/spaces, and `.`/`..` are rejected. IDs colliding
after Unicode `casefold()` are rejected. Reader angles must be finite;
`beta_tan` requires both angles in the strict principal domain and `beta_sin`
requires `abs(alpha_deg) < 90`. Bank is a finite periodic angle.

## Output

The summary CSV preserves each product's exact columns, order, total/component
rows, and blanks. Both products reject a summary path that collides with the
input table, any STL, or any planned VTP/NPZ, even when artifact save flags are
off. The complete planned artifact set is checked before execution. Collision
checks conservatively compare absolute, non-strictly resolved path components
after Unicode NFC normalization and `casefold()`, and use filesystem identity
for existing symlink or hardlink aliases. This can intentionally reject paths
that are distinct on a case-sensitive filesystem so the same case remains safe
when moved to common Windows or macOS filesystems. CSV snapshots use
same-directory temporary files, flush, `fsync`, and atomic replace.
`save_vtp_on` and `save_npz_on` select per-case artifacts under `out_dir`; the
directory side effect is retained even when both flags are off.

VTP stores geometry, panel scalars, shielding, case identity/signature, resolved
attitude, backend, compatibility version, and product-only metadata. NPZ stores
the accepted named numerical arrays and product-only values. Formats are
compared semantically by name, shape, metadata, and quantity-specific tolerance,
not by file bytes. The precise inventory is in
`phase1/BEHAVIORAL_INVENTORY.md` and the tolerances are in
`phase1/TOLERANCES.md`.

Direct Python artifact calls currently remain available on a best-effort basis:

```python
from fmfsolver.io.exporters import export_npz, export_vtp

export_vtp(
    out_path="case.vtp",
    vertices=vertices,
    faces=faces,
    cell_data=cell_data,
    field_data=field_data,
)
export_npz(out_path="case.npz", **arrays)
```

The same names are available from `newtsolver.io.exporters`. Both functions
currently write the supplied `out_path` and return `None`. ADR 0008 does not
freeze exact keyword names, object identity, defining module, or return-type
quirks for direct Python helpers.

Direct `fmfsolver.core.solver` and `newtsolver.core.solver` calls currently
retain the recorded blank/type behavior. In `run_case()` dictionaries and `run_cases()`
DataFrames, total-row `component_id` and `component_stl_path` values are empty
strings. Multi-STL component IDs are Python integers in input-STL order, and
component `vtp_path`/`npz_path` values are empty strings because artifact paths
belong only to the total row. Disabled total artifact paths are also empty
strings. These are compatibility values rather than missing-value sentinels;
callers should not expect `None`, `NaN`, or floating-point component IDs.

Direct `run_case()` and `run_cases()` are best-effort Python APIs. Callers that
bypass the file reader must supply the fields their adapter needs; these calls
do not promise the CSV/Excel reader's default insertion.

For multi-STL `run_case()` results, each dictionary in `component_rows` has
exactly these keys in this order: `scope`, `component_id`,
`component_stl_path`, `CA`, `CY`, `CN`, `Cl`, `Cm`, `Cn`, `CD`, `CL`, `faces`,
`shielded_faces`, `vtp_path`, `npz_path`. Case identity, version, signature,
timing, and backend fields belong to the total result. `run_cases()` DataFrames
and written summary CSVs retain their full schemas; this nested-record contract
does not remove columns from those surfaces. Single-STL `run_case()` results
retain an exact empty `component_rows` list.

### Direct common-core flow direction

The compatibility CLI and GUI adapters deterministically resolve
`velocity_hat_stl` and tangent angles together from each legacy attitude mode.
Equivalent attitudes expressed through different modes can therefore retain
last-bit-distinct vectors while sharing the frozen resolved-angle public
signature. Custom callers of `panelsolver.core.execute_case` should use the
shared frame helper when constructing an angle-defined request. The direct
request validator accepts a supplied unit vector within `1e-12` of the
angle-derived vector and evaluates the supplied values.

Phase 8 isolates every exact accepted vector in the private result cache, but the
frozen public signature remains angle-based. Consequently, equivalent legacy
modes or custom tolerance-distinct vectors can have last-bit numerical
differences and the same public artifact signature; do not rely on signature
alone to distinguish those artifacts. Treat a `ResultCache` passed to
`execute_case` as engine-owned: its generic `get` and `put` API is unchanged, but
the returned public signature does not address or pre-seed the engine's private
entry.

## Environment precedence

For every setting, an explicit API/configuration argument wins. The neutral
name then wins over the prefix belonging to the selected product; core never
mixes both product prefixes:

| Setting | Order after explicit argument | Default |
|---|---|---:|
| shielding cache maximum | `PANELSOLVER_SHIELD_CACHE_MAX`, then `FMFSOLVER_SHIELD_CACHE_MAX` or `NEWTSOLVER_SHIELD_CACHE_MAX` | 1; 0 disables |
| shielding ray batch | `PANELSOLVER_SHIELD_BATCH_SIZE`, then selected legacy prefix | Embree 64; rtree 8 |
| scheduler chunk cases | `PANELSOLVER_PARALLEL_CHUNK_CASES`, then selected legacy prefix | 8 |

Values must be integers in the documented positive/nonnegative domain. Both
products use common `FORWARD / YIELD_COMPLETED` behavior: worker logs and
warnings are forwarded, and prior successful cases from a later-failing chunk
remain in input-ordered progress, checkpoints, and summary results while the
remote failure is retained. Already-written per-case artifacts are not rolled
back.

### Current direct Python cancellation and failures

The following details are retained as implementation and diagnostic history.
ADR 0008 does not freeze exact direct-Python exception messages, chains,
tracebacks, validation timing, logging order, or product-specific failure
envelopes.

The frozen `fmfsolver.core.solver` and `newtsolver.core.solver` Python APIs use
their legacy built-in exceptions. A true `run_cases(..., cancel_cb=...)`
callback raises `RuntimeError("Canceled by user.")`, including for an empty input
table. A negative `flush_every_cases` still raises
`ValueError("flush_every_cases must be >= 0.")` before the cancellation callback
is consulted. A direct `run_case()` reports case-owned warnings but does not
print the ray-backend hint or batch `[RUN]`/`[OK]` messages, and it does not use up
the one-time hint. The first non-cancel empty `run_cases()` call prints only that
product's backend hint and returns an empty DataFrame; later calls are silent.
If its log callback raises, the same exception is returned and the hint remains
available for retry. FMF and newtsolver track this state independently. In
parallel execution the request is polled while workers start and remains immediate:
results still active in workers are not added to progress or checkpoint
snapshots. Files written before the request is observed, or by an in-flight
worker before cancellation cleanup finishes, are not rolled back; callers must
treat failed-run artifact paths as partial run state.

A missing STL raises `FileNotFoundError` from serial `run_case()` or
`run_cases()` calls. From a parallel worker it raises a built-in `RuntimeError`
whose first line starts `[WorkerError]` and whose remaining text contains the
remote traceback. Other caught worker Python exceptions use the same
`[WorkerError]` form. FMF and newtsolver both apply the common D015 policy
described above: worker logs are forwarded and completed results from a
later-failing chunk are yielded.

The public compatibility scheduler also retains product-specific unexpected-exit
wording and its historical empty-Queue exception context. A broken Pipe frame
retains its EOF/OSError chain instead. The adapter exposes raw spawn-start or
callable-pickling exceptions; other IPC, serialization, or cleanup failures for
which the pinned Queue scheduler could hang instead return a bounded built-in
`RuntimeError` diagnostic. Exceptions raised by a caller's `logfn`,
`progress_cb`, `cancel_cb`, or `chunk_cb` pass through unchanged. These rules
apply to the frozen direct Python interfaces; shared internal runtime, CLI, and
GUI code continues to use typed scheduler exceptions for lifecycle handling.
If a worker exits before reporting ready and its exit code is available, it uses
the same product-specific unexpected-exit wording and empty-Queue context; an
unresolved live-process transport failure remains a startup error with its
EOF/OSError chain. Cleanup diagnostics discovered while a caller callback is
unwinding are attached as notes to that same callback exception object. This
also applies to parent-side progress, checkpoint, and `[OK]` callbacks after a
parallel result is yielded: the active scheduler iterator is closed before the
original callback exception returns to the caller.

## Current historical differences

Phase 7 did not choose between several product contracts. Phase 8 has converged
XLS dispatch, case-ID/duplicate and attitude rules, mesh safety, CLI `--cases`,
output collision/CSV durability, and scheduler logs/partial results. Retained
differences include model fields and formulas, legacy signatures, model-only
CSV/VTP/NPZ fields, GUI titles/overlays, and D025 Python exports. The historical
observation ledger remains `phase1/LEGACY_DIFFERENCES.md`; ADR 0008 determines
which observations belong to the supported contract.

## Release

`CHANGELOG.md` is the source of truth for release notes. A release change must
update all of the following together:

1. Set `project.version` in `pyproject.toml`, then run `uv lock` so the editable
   `panel-solvers` package version in `uv.lock` matches.
2. Move the applicable `CHANGELOG.md` entries from `[Unreleased]` into a
   non-empty `## [<version>] - YYYY-MM-DD` section and retain a fresh
   `[Unreleased]` section.
3. Update current distribution-version references in `README.md`,
   `docs/development/setup-and-testing.md`, and this guide. Do not change the independent FMF
   `1.3.8` or newtsolver `1.0.3` compatibility versions.
4. Run the locked full suite, Ruff, build, the version-independent wheel
   reinstall/smoke, both unchanged samples, and both manual macOS GUI smokes.
   `python scripts/release_tools.py dry-run . --version <hypothetical-version>`
   exercises a temporary copy and must also pass without changing the checkout.
5. Require successful Ubuntu, Windows, macOS, and artifact CI. Fetch protected
   `origin/main` immediately before tagging and record its HEAD commit. The
   release policy does not publish an older main commit or a side-branch commit.
6. Create an annotated tag at that exact protected `origin/main` HEAD:
   `git tag -a v<version> <origin-main-head-sha> -m "panel-solvers v<version>"`.
   Verify `git rev-parse v<version>^{}` equals
   `git rev-parse refs/remotes/origin/main^{commit}` before
   `git push origin v<version>`. The tag workflow independently fetches
   `origin/main` and repeats this target check together with the project, lock,
   tag, and changelog checks. If main advances after tagging, the workflow fails
   instead of publishing the older candidate.
7. The tag workflow's `artifact` job builds exactly one wheel and one source
   distribution, records their filenames, SHA-256 values, wheel METADATA, and
   commit SHA in a machine-readable manifest, and verifies that manifest. The
   three OS jobs, installed-wheel smoke, rollback/return probe, artifact audit,
   and release job download and reuse those exact files; none rebuilds the
   candidate distributions. The GitHub Release publishes the same verified
   wheel, sdist, manifest, and matching `CHANGELOG.md` section. Both products
   always ship together.

No Phase 7 acceptance tag is created automatically by the migration PR.

## Rollback

Keep input and result files; rollback does not require converting them. The
release tags for the two legacy products predate the accepted oracle commits,
so do not use release-tag artifacts as substitutes. Build wheels from the exact
commits in `MIGRATION_SOURCES.md` through a read-only archive:

```bash
python scripts/probe_legacy_rollback.py . \
  --artifact-dir /absolute/path/to/rollback-artifacts \
  --fmf-source /absolute/path/to/clean/fmfsolver \
  --newt-source /absolute/path/to/clean/newtsolver
```

The two source arguments may instead be their official HTTPS repository URLs.
Local sources must be clean. The probe verifies the exact commit objects,
creates temporary sources with `git archive`, never checks out or modifies the
legacy repositories, builds the two wheels with each commit timestamp as
`SOURCE_DATE_EPOCH`, and writes `rollback-record.json` with repository URL,
commit, tree SHA, wheel metadata, and SHA-256.

The Phase 8 local verification on Python 3.12.12 and uv 0.9.13 produced the
same wheel digests in two independent builds:

| Product | Commit | Tree | Wheel SHA-256 |
|---|---|---|---|
| FMF 1.3.8 | `b62bc844d02a8f5212e62a53dea3238a1414317d` | `52e5b876544d90323fa04468fc22ea0fbbf559c3` | `bb42ef01f1af0ac8821ee70f239db7f53b7355dcb674567620ed8f6d618e1933` |
| newtsolver 1.0.3 | `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70` | `48e3782dd27056e716884a30e72a2ed758e6c8e4` | `6bc2bb436eea3b246549f78493edaab8679947b31c0702de8df278a02ab3939c` |

Treat the probe's record as authoritative for a new build environment; a build
tool change can alter archive bytes without changing the verified source tree.

The same probe creates a clean temporary environment and executes both sides of
the transition: install the current built `panel-solvers` candidate, verify all
six commands, uninstall it, install both pinned legacy wheels, verify all six
commands and one committed sample per product, then uninstall both legacy
distributions and reinstall the candidate wheel with both samples. It deletes
the temporary environment but retains the artifacts and evidence record.

For an operational rollback using those recorded wheels, keep the removal and
install order exact:

```bash
python -m pip uninstall panel-solvers
python -m pip install \
  /absolute/path/to/rollback-artifacts/legacy/fmfsolver/fmfsolver-1.3.8-*.whl \
  /absolute/path/to/rollback-artifacts/legacy/newtsolver/newtsolver-1.0.3-*.whl
fmfsolver-cli --input /path/to/fmfsolver/samples/input_template.csv \
  --cases baseline_cube_modeA --workers 1 --flush-every-cases 0
newtsolver-cli --input /path/to/newtsolver/samples/input_template.csv \
  --cases satellite_baseline_newtonian --workers 1 --flush-every-cases 0
```

Return to the shared distribution in the opposite order:

```bash
python -m pip uninstall fmfsolver newtsolver
python -m pip install /absolute/path/to/panel_solvers-<version>-py3-none-any.whl
python -c 'import importlib.metadata as m; print(m.version("panel-solvers"))'
fmfsolver-cli --help
newtsolver-cli --help
```

Never layer legacy wheels over `panel-solvers`, or `panel-solvers` over either
legacy distribution. The repositories themselves remain unmodified and
unarchived references.
