# User documentation layout

The MkDocs navigation owns the current page inventory. Each section's canonical
pages live directly in its corresponding directory; `docs/index.md` is the home
page. Keep navigation labels and page headings independent of file placement.

## Section roles

| Section | Directory | Role |
|---|---|---|
| Getting started | `getting-started/` | Installation and a first supplied-example run. |
| Guides | `guides/` | Task-based instructions in plain language. Link to Reference for exact rules instead of repeating them. |
| Reference | `reference/` | Exact case-table columns, result fields, Python API, and settings. These pages carry the documented compatibility surface. |
| Methods | `methods/` | Equations, conventions, and model assumptions. |
| About | `about/` | Compatibility policy, data provenance, and licenses. |

Implementation mechanisms that users do not need in order to operate the
product belong in `devdocs/`, not in user pages; see
[Detailed user-visible behavior](../architecture/detailed-user-behavior.md). Documented file semantics,
numerical conventions, and supported commands stay in user Reference pages.

## Migration inventory

Starting main: `2cf18ad`, after PR #323. Paths are relative to `docs/`.
Home (`index.md`), Getting started, and Methods pages keep their paths.

| Navigation item | Previous canonical path | Current canonical path |
|---|---|---|
| Preparing cases | `inputs/case-files.md` | `guides/preparing-cases.md` |
| Using the GUI | `running/gui.md` | `guides/gui.md` |
| Viewing results in the GUI | `running/gui.md#view-and-export` | `guides/gui-viewer.md` |
| Using the CLI | `running/cli.md` | `guides/cli.md` |
| Sectional loads and Cp | `running/gui.md` and `running/cli.md` sectional sections | `guides/sectional.md` |
| Batch runs and recovery | `running/batch-execution-and-recovery.md` | `guides/batch-runs.md` |
| Troubleshooting | `running/troubleshooting.md` | `guides/troubleshooting.md` |
| FMF case table | `inputs/fmf-input.md` | `reference/fmf-case-table.md` |
| Hypersonic case table | `inputs/hypersonic-input.md` | `reference/hypersonic-case-table.md` |
| Sectional definition CSV | `inputs/sectional-loads.md`, `inputs/sectional-cp.md` | `reference/sectional-definitions.md` |
| Summary CSV | `results/summary-csv.md` | `reference/summary-csv.md` |
| VTP | `results/vtp.md` | `reference/vtp.md` |
| Sectional load CSV | `results/sectional-loads-csv.md` | `reference/sectional-loads-csv.md` |
| Sectional Cp CSV | `results/sectional-cp-csv.md` | `reference/sectional-cp-csv.md` |
| Python API | `running/python-api.md` | `reference/python-api.md` |
| Environment variables | `product-reference/environment-variables.md` | `reference/environment-variables.md` |
| Compatibility and versioning | `product-reference/compatibility.md` | `about/compatibility.md` |
| US1976 data provenance | `appendix/us1976-data-provenance.md` | `about/us1976-data-provenance.md` |
| License and third-party notices | `appendix/license-and-third-party-notices.md` | `about/license-and-third-party-notices.md` |

## Old URLs

Previous canonical paths are removed. No compatibility pages or redirects are
shipped, so old page URLs and their deep-anchor URLs no longer resolve; use the
current paths above. Headings on moved pages are unchanged, except for sections
merged into `guides/sectional.md` and `reference/sectional-definitions.md`,
which received unique headings on their new page.

All Markdown pages under `docs/` are canonical navigation pages. Historical
records retain their recorded paths and are not current navigation sources;
links in the history index to current user documentation follow the new
locations.

## Verification when changing the layout

`tests/unit/test_docs_site.py` checks section ownership, exact agreement between
the navigation and Markdown page inventory, all generated local links/fragments,
local image and stylesheet resources, and prerendered MathML. Run
`python scripts/check.py` for the standard gate, including strict MkDocs and
distribution builds. Verify that the wheel and release docs archive contain the
full generated page set and no removed compatibility pages.
