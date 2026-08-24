# ADR 0010: Remove legacy BIFF XLS input support

- Status: Accepted
- Date: 2026-08-15
- Supersedes: only the legacy BIFF `.xls` case-file portion of ADR 0008

## Context

The `.xls` extension represents the legacy Excel 97–2003 BIFF workbook format.
The current product's case-table needs are fully covered by CSV and the OOXML
XLSX/XLSM formats, and there are no known users of `.xls` input.

Supporting `.xls` solely for that unused format requires the `xlrd` runtime
dependency, a dedicated reader branch, committed BIFF fixtures, and a separate
test path. That maintenance surface has no current product value.

This is an intentional input-compatibility change, not a numerical-model change.
Phase 1 `.xls` fixtures, captures, provenance, hashes, and migration records
remain historical evidence of the pinned legacy products.

## Decision

The current product supports exactly CSV, XLSX, and XLSM case tables. Remove
legacy `.xls` input immediately, without a deprecation period, compatibility
wrapper, optional `xlrd` dependency, automatic conversion, or attempt to read
`.xls` as another format.

Reject `.xls` case paths before any workbook reader is invoked and provide a
migration message. Users must resave the workbook as `.xlsx` in Excel or another
spreadsheet application, or export it as CSV.

This decision supersedes only ADR 0008's legacy BIFF `.xls` case-file support.
ADR 0008's CSV, XLSX, XLSM, VTP, numerical, and other supported-domain decisions
remain in force.

The pinned legacy FMF and newtsolver implementations retain their historical
`.xls` support. Their Phase 1 evidence and independent pinned environments are
not changed or regenerated.

This change does not alter numerical behavior, solver models, VTP semantics,
Summary CSV semantics, case signatures, shielding, mesh behavior, scheduling,
cancellation, caches, GUI viewing, or output paths. The `panel-solvers`
distribution version and the FMF/newtsolver compatibility versions are not
changed by this implementation PR.

## Consequences

The current runtime no longer includes `xlrd`, the BIFF reader branch, or
current-schema BIFF fixtures and tests. CSV, XLSX, and XLSM retain their existing
column order, defaults, path resolution, unknown-column behavior, calculations,
and outputs.

Users with historical `.xls` case files perform a one-time resave to `.xlsx` or
CSV export before using a current `panel-solvers` release. A pinned legacy
version remains available when reproducing historical `.xls` behavior.
