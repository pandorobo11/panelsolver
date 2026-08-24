# Third-party and public-domain notices

This file records material and dependencies that are not relicensed by the
Panel Solver Apache License 2.0. It is informational and is not an Apache
`NOTICE` file.

## U.S. Standard Atmosphere, 1976

- Title: *U.S. Standard Atmosphere, 1976*
- Report identifiers: NOAA-S/T-76-1562 and NASA-TM-X-74335
- NASA Technical Reports Server document ID:
  [19770009539](https://ntrs.nasa.gov/citations/19770009539)
- NTRS rights record: `Distribution Limits: Public`; `Copyright: Work of the
  US Gov. Public Use Permitted`

Panel Solver uses a generated 201-row table of geometric altitude,
temperature, speed of sound, and mean molecular speed for the FMF/Sentman Mode
B atmosphere calculation. The underlying U.S. Government report and physical
data are not claimed as copyright of pandorobo11. Scientific and model-facing
provenance is documented in
[US1976 Sentman atmosphere data provenance](docs/reference/us1976-data-provenance.md).
Maintainer regeneration steps and audit records are stored in repository and
source-distribution path `devdocs/data/us1976-generation-and-audit.md`; that
developer page is not included in GUI Help, the wheel documentation site, or
the standalone documentation ZIP.

## Public Domain Aeronautical Software

The regeneration source is the `bigtables.py` program version 1.5 from the
Public Domain Aeronautical Software (PDAS) atmosphere package:

- upstream package: `https://www.pdas.com/packages/atmos.zip` (retrieved
  2026-08-15);
- package SHA-256:
  `6ede29f1e4f104ad3d5cbe990071682fd903ab04d7d47b168a4c17817714365a`;
- upstream `bigtables.py` SHA-256:
  `eca87577139ac3b2845d1d4eca91604ac278a491918979f2d2316bf88a9a3a28`;
- repository minimal calculation snapshot:
  `tools/reference/pdas/bigtables_v1_5.py`;
- snapshot SHA-256:
  `11e82d35d66a61c4326acf04fcad0c9ab471112721151b65cfdf4faff43f9994`.

The [PDAS legal statement](https://www.pdas.com/legal.html) distinguishes the
compilation copyright in the collection from its individual programs. It
states that the individual programs are public domain and that PDAS-added
program value is donated to the public domain. The repository uses and
redistributes only the minimal calculation snapshot needed for deterministic
regeneration. It does not vendor the PDAS Web site, `bigtables.html`, or the
PDAS collection as a whole.

The underlying PDAS program is not claimed as copyright of pandorobo11 and is
not relicensed under Apache-2.0.

## Scientific methods and citations

The Sentman, Newtonian, Modified Newtonian, tangent-wedge, tangent-cone,
Taylor--Maccoll, and Prandtl--Meyer implementations use mathematical equations,
physical methods, and algorithms described by the technical sources cited in
the solver documentation. Those citations are technical provenance; they are
not third-party software licenses. The project does not redistribute source
publication figures or publication prose.

## Offline documentation static assets

The wheel and standalone documentation ZIP redistribute the generated MkDocs
site, including theme CSS, JavaScript, images, and webfonts. This content is a
vendored release-artifact exception to the separately installed dependency
boundary described below. The site uses the built-in `readthedocs` theme from
the locked MkDocs 1.6.1 distribution. The external `sphinx-rtd-theme` Python
package is not installed or added as a runtime dependency. MkDocs carries an
adapted Sphinx RTD Theme asset snapshot. MkDocs made changes to both the CSS
updated from Sphinx RTD Theme 1.2.0 and the separately loaded theme JavaScript,
which retains the upstream 1.0.0 build header and navigation behavior carried
forward in 1.2.0. The JavaScript also embeds the webpack bootstrap runtime and
an independently licensed requestAnimationFrame polyfill. The versions below
are established from the MkDocs 1.6.1 source and theme-upgrade history, the
Sphinx RTD Theme 1.2.0 tag and lockfile, tagged component sources, file headers,
and embedded font metadata.

| Redistributed content | Copyright holder | License | Required preservation |
|---|---|---|---|
| MkDocs 1.6.1 templates, adaptations in `css/theme.css` and `js/theme.js`, `theme_extra` CSS/JS, and favicon | Copyright © 2014-present Tom Christie | BSD-2-Clause | copyright, conditions, and disclaimer |
| Sphinx RTD Theme 1.2.0 CSS and navigation JavaScript source adapted by MkDocs | Copyright © 2013-2018 Dave Snider, Read the Docs, Inc. and contributors | MIT | copyright and permission notice |
| Wyrm 1.0.9 styles compiled into `css/theme.css` | Copyright © 2013 Dave Snider | MIT | copyright and permission notice |
| Bourbon 4.3.4 styles compiled into `css/theme.css` | Copyright © 2011-2017 thoughtbot, inc. | MIT | copyright and permission notice |
| Bourbon Neat 1.9.1 styles compiled into `css/theme.css` | Copyright © 2012-2015 thoughtbot, inc. | MIT | copyright and permission notice |
| Font Awesome 4.7.0 CSS and webfonts | Copyright Dave Gandy 2016 | MIT for CSS; SIL OFL 1.1 for webfonts | component/version attribution and complete MIT/OFL texts; the unmodified FontAwesome family name is retained (the tagged upstream notice does not declare a Reserved Font Name) |
| Lato 3.0.0 package webfonts (font version 2.015) | Copyright © 2010-2015 Łukasz Dziedzic / tyPoland | SIL OFL 1.1 | copyright and complete OFL text; Reserved Font Name `Lato` retained because the font files are unmodified |
| Roboto fontface 0.10.0 package's Roboto Slab webfonts (font version 1.100263) | Font data copyright Google 2013 | Apache-2.0 | upstream path scope and complete Apache-2.0 text |
| jQuery 3.6.0 | Copyright OpenJS Foundation and other contributors | MIT | copyright and permission notice |
| HTML5 Shiv 3.7.3 | Copyright © 2014 Alexander Farkas | MIT OR GPL-2.0-only; redistributed under the MIT option | upstream dual-license statement and complete MIT/GPL-2.0 texts |
| webpack 4.46.0 bootstrap runtime embedded in `js/theme.js` | Copyright JS Foundation and other contributors | MIT | copyright and permission notice |
| requestAnimationFrame polyfill embedded in `js/theme.js` | By Erik Möller; fixes from Paul Irish and Tino Zijdel (the upstream source provides no separate copyright line) | MIT | upstream attribution and complete permission notice |

The required copyright notices and license texts are preserved under
`THIRD_PARTY_LICENSES/`. That directory and this notice are copied into
`panelsolver/_docs_site/` in the wheel and therefore into the byte-equivalent
documentation ZIP alongside the generated CSS, JavaScript, image, and font
files. The same license files are also recorded as wheel metadata license
files. All static references are local; no CDN, external font, or external
JavaScript is required. These third-party works are not covered or relicensed
by Panel Solver's project Apache-2.0 `LICENSE`.

The small `assets/stylesheets/panelsolver-docs.css` table-width correction and
`assets/javascripts/panelsolver-docs.js` navigation correction are Panel
Solver-owned project code under Apache-2.0; they are kept outside the
third-party theme asset prefixes and license mapping.

## Runtime dependencies

The runtime dependencies declared in `pyproject.toml`--NetworkX, NumPy,
openpyxl, pandas, PySide6, PyVista, pyvistaqt, Rich, rich-argparse, Rtree,
SciPy, and Trimesh--and the optional Embree bindings are installed as separate
distributions. They remain subject to their respective upstream licenses and
are not relicensed by Panel Solver. Consult each installed distribution and its
upstream project for its applicable license and notices.

Except for the audited offline-documentation assets above, the panelsolver
wheel does not contain runtime-dependency source or binaries. In particular,
it declares `PySide6>=6.9.3,<7` as an external dependency and does not contain
PySide6 or Qt binaries. A future standalone application bundle, for example one
produced with PyInstaller, would require a separate license and notice audit
for every bundled dependency and binary.
