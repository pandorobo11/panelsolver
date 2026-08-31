# ADR 0015: Remove legacy product identities and artifact fallback

- Status: Accepted
- Date: 2026-08-31
- Supersedes: the compatibility-frontend and package/command portions of ADR
  0001, ADR 0003, ADR 0004, ADR 0007, ADR 0008, ADR 0011, ADR 0013, and ADR
  0014; the legacy-signature portions of ADR 0005, ADR 0007, ADR 0012, and ADR
  0014

## Context

Before the first Panel Solver release, the distribution still exposed two
predecessor-product package identities, six command aliases, product-specific
tuning-variable fallbacks, and reconstruction of D017/D018 VTP signatures. No
external users have been identified who require those surfaces. Retaining them
would make a temporary migration boundary part of the first public contract and
would require permanent packaging, GUI-identity, release, and artifact-matching
branches.

The canonical `panelsolver.case` version 1 signature remains necessary. It
prevents an automatically discovered VTP from being displayed for a stale or
mismatched current case without coupling case identity to the distribution
version.

## Decision

Panel Solver exposes only its canonical `panelsolver` distribution, Python
package, package-root API, `panelsolver` batch command, and `panelsolver-gui`
graphical command. The batch and GUI commands select the `fmf` or `hypersonic`
flow domain. Predecessor-product package and command identities and their
product-specific tuning-variable aliases are removed without a deprecation
period, warning shim, tombstone package, or migration command.

The old products' VTP signatures are no longer reconstructed or accepted. Core
and GUI composition use one `CaseSignature` directly rather than a primary-plus-
fallback candidate collection. Automatic artifact loading requires equality of
both the current case ID and the current canonical signature. Existing canonical
signature construction, schema, payload, and digests remain unchanged.

Manual **Open VTP...** remains a generic inspection path. A historical file may
open if it satisfies the current viewer's data requirements, but historical VTP
compatibility is not supported and no old scalar alias, parser, converter, or
explicit version rejection is added. Users can regenerate artifacts with Panel
Solver.

Historical numerical evidence remains valid test and reference material. Frozen
Phase 1 inputs, coefficients, per-panel arrays, masks, CSV/VTP semantics,
tolerances, and source provenance may retain historical names without becoming a
public package, command, or artifact-compatibility contract.

This is intentional first-release cleanup. It changes no physical equation,
algorithm, sign, frame, normalization, numerical tolerance, current case-file
schema, current CSV/VTP schema, `solver_version` behavior, or canonical signature
digest.

## Consequences

The wheel contains only the `panelsolver` package and registers exactly the
`panelsolver` and `panelsolver-gui` console scripts. Environments and automation
using predecessor-product names must move directly to the canonical selectors.
Historical VTPs are stale or mismatched for automatic display unless they happen
to carry the exact current canonical identity; predecessor signatures are not a
fallback. Release and installed-wheel gates verify the exact package and command
surface, canonical domain dispatch, stable package-root API, current artifact
matching, and absence of the removed packages.
