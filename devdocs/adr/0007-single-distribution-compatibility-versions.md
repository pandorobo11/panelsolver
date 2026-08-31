# ADR 0007: Release one distribution with distinct compatibility versions

- Status: Accepted
- Date: 2026-08-12

The Summary CSV and VTP version-metadata portion of this decision is superseded
by [ADR 0012](0012-runtime-artifact-distribution-version.md). Its packaging,
release-tag, and legacy-signature decisions remain in force.

The distribution name and corresponding metadata lookup/uninstall spelling are
superseded by [ADR 0013](0013-canonical-project-identity.md). The historical
`panel-solvers` wording below records the decision as accepted at the time.

The best-effort direct-Python and legacy Python version-name portions are
superseded by [ADR 0014](0014-remove-legacy-direct-python-api.md). The historical
versions remain private legacy-signature inputs.

The compatibility-package, command, compatibility-version, legacy-signature,
and rollback portions are superseded by
[ADR 0015](0015-remove-legacy-product-identities.md). The one-distribution and
release-tag decisions remain in force.

## Context

ADR 0001 places the shared engine, application, models, and compatibility
frontends in one repository, but it deliberately does not decide whether they
ship as one or several Python distributions. Phase 7 must register both legacy
command families, restore their import paths, and provide one rollback story.

The frozen products also expose versions in result CSV rows, VTP metadata,
legacy case signatures, and the newtsolver Python surface. Those values are
`1.3.8` for FMF and `1.0.3` for newtsolver at the pinned commits. The neutral
project currently has distribution version `0.1.0`. Treating these values as one
version would either break frozen compatibility or misrepresent the neutral
distribution's release history.

## Decision

Publish one Python distribution named `panel-solvers`. Its wheel contains the
`panelsolver`, `fmfsolver`, and `newtsolver` packages and owns all six console
scripts. The compatibility packages remain thin frontends; no separate FMF or
newtsolver wheel is built from this repository.

`project.version` is the shared distribution version and is the only value used
for repository release tags. A release tag is exactly `v<project.version>`.

The compatibility frontends independently retain these product compatibility
versions until a separately approved compatibility transition changes them:

| Frontend | Compatibility version |
|---|---:|
| `fmfsolver` | `1.3.8` |
| `newtsolver` | `1.0.3` |

The product compatibility version is used only where the pinned public contract
already exposes a product version: compatible result CSV cells, VTP metadata,
legacy signature reconstruction, and legacy Python version names. It is not the
installed distribution version and does not claim that the implementation is
still the legacy code. The canonical Phase 5 signature continues to identify
the actual geometry, model algorithm version, and shielding algorithm; it does
not use either application version.

Installed-distribution inspection must use
`importlib.metadata.version("panel-solvers")`. Compatibility code must not ask
for nonexistent `fmfsolver` or `newtsolver` distribution metadata.

One release publishes the wheel and source distribution only after both product
command, import, sample, artifact, GUI, and cross-platform gates pass. Rollback
removes `panel-solvers` before reinstalling either legacy distribution, because
the distributions provide overlapping top-level package and command names.
Legacy repositories remain available and are not archived before Phase 8.

## Consequences

Users install and update one artifact, and shared changes cannot produce a
partially updated product pair. Both compatibility contracts must therefore pass
for every release, even when a change appears product-specific.

The separate compatibility constants are deliberate adapter policy, not package
version aliases. A future change to either constant requires migration notes,
tests for old artifacts/signatures, and an explicit compatibility decision.
Phase 7 introduces no deprecation or removal schedule for the old names.

The single wheel makes rollback ordering important and prevents simultaneous
installation with either legacy distribution from being a supported state.
