# Release and rollback

One Panel Solver release contains the shared engine, both physical models, both
compatibility packages, the canonical commands, and all six legacy commands.

## Version and release identity

`project.version` in `pyproject.toml` is the only distribution-version source of
truth. The `panelsolver` entry in `uv.lock` must match it. `CHANGELOG.md` is the
release-note source. A release tag is exactly `v<project.version>`, must be an
annotated tag, and must target the exact latest protected `origin/main` commit.

FMF `1.3.8` and newtsolver `1.0.3` remain historical compatibility baselines;
they are not distribution versions. Runtime lookup uses
`importlib.metadata.version("panelsolver")`.

## Build-once artifact contract

The artifact job builds and uploads exactly this set once:

1. `panelsolver-<version>-py3-none-any.whl`;
2. `panelsolver-<version>.tar.gz`;
3. `panelsolver-docs-v<version>.zip`;
4. `panelsolver-examples-v<version>.zip`;
5. `manifest.json`.

The wheel and sdist filenames are taken from the build backend output. The
documentation ZIP is created from the already-built wheel's bundled
`panelsolver/_docs_site/` tree, so it is byte-equivalent to GUI Help. The
documentation ZIP does not contain `devdocs/`. The examples ZIP contains only
current `examples/fmf/`, `examples/hypersonic/`,
`examples/geometry/`, `examples/README.md`, `LICENSE`, and
`THIRD_PARTY_NOTICES.md`; generated outputs, caches, NPZ, legacy `.xls`, test
fixtures, and historical migration inputs are excluded.

Both ZIPs normalize ordering, timestamps, permissions, separators, compression,
and metadata. Rebuilding either from identical source must produce an identical
SHA-256 digest.

Test and release jobs download the internal
`panelsolver-dist-${{ github.run_id }}` artifact, verify it, and reuse it. They
must not run `uv build`, `mkdocs build`, or rebuild either ZIP. The sdist rebuild
is an isolated verification artifact and is never published in place of the
original wheel.

## Manifest schema v2

`manifest.json` uses `panelsolver.dist-manifest` schema version 2. Its ordered
`artifacts` array contains exactly `wheel`, `sdist`, `docs`, and `examples`, each
with the exact filename and SHA-256; the wheel record also includes its METADATA
name and version. `github_commit_sha` binds the set to the workflow commit.

Verification rejects missing or extra artifacts, duplicate or reordered kinds,
duplicate or unexpected filenames, hash or commit changes, wheel Name/Version or
`project.version` mismatch, and any difference between the documentation ZIP and
the wheel-bundled site.

Wheel verification checks the packaged offline documentation and its canonical
solver pages, required packaged examples, project name/version and publication
metadata, license and third-party notice files, and the audited theme-asset
license mapping. It also rejects developer or removed documentation and rejects
MkDocs or LaTeX-to-MathML tooling in runtime requirements. Those tools are
exact-pinned build/development dependencies because the generated static assets,
MathML, and third-party license inventory are part of the audited release
artifact contract.

Sdist verification instead checks the source inputs needed for an isolated wheel
rebuild. The sdist build configuration includes the project source and examples;
verification requires the complete regular-file trees under `docs/` and
`devdocs/`, `mkdocs.yml`, documentation build support, `hatch_build.py`, key
project source and example inputs, the deterministic US1976 generator and
generated source, the pinned PDAS reference snapshot, and the root legal files.
The isolated rebuild then verifies the resulting wheel through the wheel checks
above.

## Release gates

Before publishing, CI verifies:

- generated US1976 and documentation-plot sources;
- strict offline docs, local assets, links, and MathML rendering;
- the original wheel in a fresh dependency-installed environment outside the
  checkout, including canonical/legacy commands, stable Python API, actual FMF
  and Hypersonic solves, all representative release examples, packaged docs,
  and offscreen GUI construction;
- an isolated wheel rebuild from the sdist, followed by install, resource,
  metadata, and canonical command smoke checks;
- unchanged regression, compatibility, scheduler, rtree, and available Embree
  behavior on Ubuntu, Windows, and macOS;
- annotated tag, matching version and lock, nonempty matching CHANGELOG section,
  exact protected-main target, and a successful latest `CI` workflow run for
  the exact commit from a normal `main` push; tag and pull-request runs and
  obsolete earlier runs are not release-acceptance inputs;
- repository identity `pandorobo11/panelsolver`, zero open non-PR issues, and
  zero open pull requests.

Only after those gates does the release job publish the downloaded verified set.
The matching CHANGELOG section supplies release notes. A version containing an
alpha, beta, or RC marker such as `0.2.0rc1` creates a GitHub prerelease; a stable
`<version>` creates a normal release.

## Preparing a release candidate

After the intended release changes are merged and the exact protected-main CI
is green:

1. create an RC preparation branch from latest protected main;
2. set `project.version = <rc-version>` using an identifier such as `0.2.0rc1`;
3. run `uv lock` and verify the `uv.lock` `panelsolver` version;
4. move current Unreleased notes into a dated `[<rc-version>]` section;
5. create a fresh `[Unreleased]` section;
6. run the full CI and merge the independent RC preparation PR;
7. confirm the merged exact-main CI is completely successful;
8. create annotated tag `v<rc-version>` on that exact main commit;
9. verify the resulting GitHub prerelease and its exact five attachments.

## Distribution licensing boundary

The Python wheel declares runtime dependencies but does not vendor their source
or binaries. The separately audited static assets inside the generated offline
documentation are the exception and carry their own license texts under
`THIRD_PARTY_LICENSES/`. PySide6 and Qt remain separate distributions installed
by pip. Before publishing a standalone bundle that embeds Qt or another
dependency, perform a separate audit for those exact files. The root `LICENSE`,
`THIRD_PARTY_NOTICES.md`, and third-party license directory remain authoritative.

## Roll back to pinned legacy implementations

The shared distribution and legacy distributions must not coexist. Pinned source
commits are recorded in
[Migration sources](../history/migration/MIGRATION_SOURCES.md). The repository's
`scripts/probe_legacy_rollback.py` verifies those commits and can build recorded
rollback wheels from clean local sources or official HTTPS URLs.

Operational order:

```bash
python -m pip uninstall panelsolver
python -m pip install /path/to/fmfsolver-1.3.8-*.whl /path/to/newtsolver-1.0.3-*.whl
```

Return to Panel Solver in the opposite order:

```bash
python -m pip uninstall fmfsolver newtsolver
python -m pip install /path/to/panelsolver-<version>-py3-none-any.whl
panelsolver --help
panelsolver fmf --help
panelsolver hypersonic --help
fmfsolver-cli --help
newtsolver-cli --help
```

Pinned legacy releases expose their historical `.xls` input and NPZ output
again. Before returning an old case to Panel Solver, convert `.xls` to `.xlsx`
or CSV and remove `save_npz_on`. Current Summary CSV has no `save_npz_on` or
`npz_path`, and Panel Solver does not create NPZ. Existing files are not deleted.
