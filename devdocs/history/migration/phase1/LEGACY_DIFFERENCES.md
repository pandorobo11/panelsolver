# Phase 1 legacy-difference ledger

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

This ledger records differences at the pinned commits. ADR 0008 now governs
which observations remain supported product contracts; the behavior columns
stay immutable evidence, while historical “preserve” guidance in the final
column is superseded where ADR 0008 selects common safety or infrastructure.
A classification is not permission to change supported numerical or file
behavior without evidence. `bug` means the
implementation contradicts its own advertised or safety contract; compatibility
handling still requires an explicit decision.  `unknown` means no evidence of
intent was found.

| ID | Surface | `fmfsolver` behavior | `newtsolver` behavior | Classification | Effect / next decision |
|---|---|---|---|---|---|
| D001 | Physical inputs | Exactly one of Mode A (`S`, `Ti_K`) or Mode B (`Mach`, `Altitude_km`), plus `Tw_K` | `Mach`, `gamma`, windward and leeward equation selectors | intentional | Model case contracts remain independent in Phase 2. |
| D002 | Local load model | Sentman vector contains normal and tangential/freestream contributions | Pressure-only vector is normal to the panel | intentional | The common boundary must be a vector, never universal scalar `Cp`. |
| D003 | Hypersonic equation selection | Not applicable | Four windward and two leeward choices; per-STL lists allowed | intentional | Model metadata and per-component selection stay in the hypersonic model. |
| D004 | `.xls` input | Dispatches `.xls` to `xlrd` | Advertises `.xls` but dispatches it to `openpyxl`, which does not read legacy BIFF XLS | bug | Decide whether compatibility preserves failure or restores advertised support in a dedicated change. |
| D005 | `case_id` character set | Portable filename checks permit a wider, potentially Unicode set | Restricts IDs to an ASCII portable pattern | compatibility decision required | A frontend may need product-specific validation. |
| D006 | Duplicate `case_id` | Exact/case-sensitive duplicate check | Case-insensitive duplicate check | compatibility decision required | Filesystems differ in case sensitivity; preserve both until policy is accepted. |
| D007 | `beta_tan` domain | `read_cases` and attitude resolver reject either angle at/outside ±90° | `read_cases` has no angle-domain check; trigonometric resolver can accept 90° through finite floating approximations | compatibility decision required | Do not normalize boundary behavior in the common attitude contract without explicit fallback. |
| D008 | CLI `--cases` cardinality | `nargs="+"`; option without a value is argument error | `nargs="*"`; option without a value becomes all cases | unknown | Six command contracts need exact compatibility tests in Phase 7. |
| D009 | Result-path collision safety | CLI rejects only summary path equal to input file | Rejects collision with input, any STL, and every planned VTP/NPZ path even when save is off | compatibility decision required | Preserve product behavior; common safe default alone would break FMF edge cases. |
| D010 | CSV durability | Same-directory temporary file, flush, `fsync`, then `os.replace` | Same-directory UUID temporary file and `os.replace`, without explicit `fsync` | compatibility decision required | Failure/durability semantics differ even though both are atomic at normal completion. |
| D011 | Mesh repair failure | Repair exceptions and remaining winding inconsistency are errors; degenerate/nonfinite faces are rejected | Repair exceptions are warnings; no explicit winding/area rejection | compatibility decision required | Highest numerical risk for Phase 3; retain separate goldens and require an ADR before selecting strictness. |
| D012 | Mesh cache file identity | Absolute path, size, mtime, ctime, inode, and scale | Absolute path, size, mtime, and scale | compatibility decision required | newtsolver can reuse stale content under more metadata-preserving replacements.  Phase 5 must define neutral identity. |
| D013 | Shield cache identity | Geometry/topology fingerprint plus normalized direction rounded to 12 decimals, batch, and backend | Separate geometry and centers digests plus normalized direction rounded to 12 decimals, batch, and backend | intentional envelope difference; shared bug | Both pinned caches can collide for distinct grazing directions whose exact masks differ. Phase 8 corrects the shared private direction identity without unifying the product-specific geometry envelopes or changing the ray algorithm. |
| D014 | Environment names | `FMFSOLVER_*` | `NEWTSOLVER_*` | intentional | Phase 5 must add `PANELSOLVER_*` precedence while continuing to read both legacy prefixes. |
| D015 | Parallel worker failure envelope | Worker log messages are forwarded; completed results are omitted when a later case in the same chunk raises a caught Python exception | Worker uses a null logger; completed results are yielded before the same-chunk error is raised | compatibility decision required | CLI/GUI logs and failure checkpoints differ under parallel runs; preserve the paired product policies and document already-written artifact behavior. |
| D016 | Scheduler grouping implementation | Includes the same high-level geometry/direction/backend reuse intent, with FMF-specific row fields | Same intent with newtsolver row/equation pipeline | intentional | Common execution can be designed later, but failure/cancel/order behavior stays fixture-backed. |
| D017 | Signature envelope | Explicit schema version 2, FMF mode fields, content digest cache | No schema-version field, hypersonic equation canonicalization, uncached digest | compatibility decision required | Both also include absolute paths and installed version.  Phase 5 must preserve relational legacy matching while adopting ADR 0005. |
| D018 | Signature defaults from direct API | Missing direct-row defaults can hash differently from file-normalized cases | Same issue, with equation defaults especially visible | bug | Do not silently repair in Phase 1; add direct/file compatibility cases before Phase 5. |
| D019 | VTP model metadata | No flow mode/S/Ti/Tw fields beyond common metadata | Adds `windward_eq_used` and `leeward_eq_used` | intentional | Viewer discovery must accept model-specific fields and arrays. |
| D020 | NPZ physical fields | Adds `S`, `Ti_K`, `Tw_K` | Adds no equation or Mach/gamma metadata | compatibility decision required | Existing omissions are frozen; a future common envelope cannot pretend legacy NPZ is complete. |
| D021 | Output-path side effect | `run_case` creates `out_dir` even when both artifact flags are off | Same side effect | intentional | This is a shared legacy quirk, not a reason to move filesystem work into the model layer. |
| D022 | GUI title | `Sentman FMF Solver (GUI)` | `newtsolver (GUI)` | intentional | Compatibility launchers must retain product identity. |
| D023 | Window close during active run | Requests cancellation and defers close until the thread exits | No equivalent `closeEvent` deferral | unknown | Phase 6 must decide lifecycle behavior without assuming either implementation is universally correct. |
| D024 | Manual stale-VTP open | Manual Open VTP displays even if no case signature matches | Same | intentional | README wording about signature matching applies to automatic/batch load, not manual inspection. |
| D025 | Python re-export surface | No explicit computational `__all__`; callers import implementation modules | `core.panel_core` and `core.pressure_models` explicitly re-export model functions, including some underscore names | compatibility decision required | Phase 2 defines neutral contracts; Phase 7 decides which de facto names frontends must forward. |
| D026 | Atmosphere data/API | Bundles US1976 tables and public sampling helpers | No atmosphere package | intentional | These remain Sentman model inputs and metadata, not common core concerns. |
| D027 | GUI active-run close tests | Explicit regression coverage exists | No close lifecycle regression | unknown | Missing coverage is evidence of uncertainty, not permission to copy FMF behavior. |
| D028 | Canonical validation strength | Sentman analytic flat-plate oracle over multiple speed ratios and angles | Newtonian analytic plate plus model-internal numerical consistency; no independent high-precision cone/PM oracle | intentional | Tangent-cone and PM fixtures freeze legacy behavior, not independent physical correctness. |
| D029 | Summary CSV model fields | Adds `mode`, `out_S`, and `out_Ti_K` to the result portion; also repeats `out_attitude_input` | Has no flow-mode/S/Ti result fields; windward/leeward equation choices remain repeated input columns, and it also repeats `out_attitude_input` | intentional | A common result envelope must preserve model-specific fields and exact product column order; neither schema is a universal superset. |

The D015 row above is a historical Phase 1 evidence record; its fact columns are
unchanged. ADR 0008 supersedes that product difference, and the current policy
for both products is `FORWARD / YIELD_COMPLETED`.

## Shared unresolved quirks

These are not differences, but they are inputs to later decisions:

- literal case signatures are clone-path and installed-version dependent;
- requested `auto` is signed, but the effective backend is not, so one signature
  can identify rtree or Embree output in different environments;
- explicit unavailable Embree raises and never falls back;
- NPZ `stl_paths` is an object array and requires trusted pickle loading;
- VTP, NPZ, and CSV each omit quantities held by the other two;
- direct Python calls bypass table validation/default insertion;
- cache identities and signature identities are not the same;
- cancellation is cooperative between cases, not immediate within a ray or ODE
  operation;
- GUI screenshot pixels are platform/OpenGL/font dependent and are not suitable
  byte goldens.

## Decisions deliberately deferred

Phase 1 did not decide the common angle boundary, case-ID policy, old XLS
support, mesh strictness, output collision policy, signature migration, cache
identity, parallel log behavior, window-close lifecycle, or de facto Python API
set. ADR 0008 now supplies the supported-domain rule: model schemas, physics,
model outputs, and migration names may differ; common infrastructure and invalid
inputs converge; direct Python details remain best effort.
