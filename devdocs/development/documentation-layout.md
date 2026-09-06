# User documentation layout

The MkDocs navigation owns the current page inventory. Each section's canonical
pages live directly in its corresponding directory; `docs/index.md` is the home
page. Keep navigation labels and page headings independent of file placement.

## Migration inventory

Starting main: `530d9d78b6d129bccd67d3d1de98f323c69b717c`, after PR #276.
Paths below are relative to `docs/`. Home (`index.md`) is unchanged.

| Navigation item | Previous canonical path | Current canonical path |
|---|---|---|
| Installation | `getting-started/installation.md` | `getting-started/installation.md` |
| Quickstart | `getting-started/quickstart.md` | `getting-started/quickstart.md` |
| Coordinate and attitude conventions | `reference/coordinate-and-attitude-conventions.md` | `methods/coordinate-and-attitude-conventions.md` |
| Load and coefficient conventions | `reference/load-and-coefficient-conventions.md` | `methods/load-and-coefficient-conventions.md` |
| FMF / Sentman model | `solvers/fmf.md` | `methods/fmf.md` |
| Hypersonic pressure methods | `solvers/hypersonic.md` | `methods/hypersonic.md` |
| Ray shielding | `reference/ray-shielding.md` | `methods/ray-shielding.md` |
| Case tables and geometry | `user-guide/case-files.md` | `inputs/case-files.md` |
| FMF input reference | `reference/fmf-input.md` | `inputs/fmf-input.md` |
| Hypersonic input reference | `reference/hypersonic-input.md` | `inputs/hypersonic-input.md` |
| GUI | `user-guide/gui.md` | `running/gui.md` |
| CLI | `user-guide/cli.md` | `running/cli.md` |
| Python API | `reference/python-api.md` | `running/python-api.md` |
| Batch execution and recovery | `user-guide/batch-execution-and-recovery.md` | `running/batch-execution-and-recovery.md` |
| Troubleshooting | `user-guide/troubleshooting.md` | `running/troubleshooting.md` |
| Summary CSV reference | `results/summary-csv.md` | `results/summary-csv.md` |
| VTP reference | `results/vtp.md` | `results/vtp.md` |
| Environment variables | `reference/environment-variables.md` | `product-reference/environment-variables.md` |
| Compatibility and versioning | `reference/compatibility.md` | `product-reference/compatibility.md` |
| US1976 data provenance | `reference/us1976-data-provenance.md` | `appendix/us1976-data-provenance.md` |
| License and third-party notices | `reference/license-and-third-party-notices.md` | `appendix/license-and-third-party-notices.md` |

## Old-link exceptions

The 17 moved pages remain at their previous paths only as unlisted link guides.
Every rendered content ID from the starting revision is retained as an explicit
anchor with a relative link to the same anchor on the current page. Opening an
old `.html#anchor` URL lands at that guide; following its link opens the current
section. This is a one-click handoff, not an automatic redirect. It works through
`file://` without JavaScript or a network connection. Canonical headings and
explicit IDs are unchanged. Markdown source links work on the repository too.

`reference/output-formats.md` was already an unlisted compatibility guide. It
continues to point to the two canonical Results references and the current input
and GUI procedures, without duplicating schemas. These 18 guides are exceptions
to the directory layout, not additional canonical references. Assets, Getting
started, Results, and the home page stay in place. No previously deleted page is
resurrected (including numerical-conventions and shielding-and-parallel).

Historical records retain their recorded paths and are not current navigation
sources. Current README, examples, developer architecture/data links, legal
notice pointers, and packaging checks follow the new canonical locations.

## Verification when changing the layout

`tests/unit/test_docs_site.py` checks section ownership, the compatibility-guide
inventory and anchor handoffs, all generated local links/fragments, local image
and stylesheet resources, and prerendered MathML. Run `python scripts/check.py`
for the standard gate, including strict MkDocs and distribution builds. Verify
that the wheel and release docs archive contain the full generated page set.
