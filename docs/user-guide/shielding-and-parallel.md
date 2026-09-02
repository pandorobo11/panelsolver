# Shielding and parallel execution

## Ray shielding

`shielding_on=1` casts an upstream ray from every face center and makes a panel's
load exactly zero when another face is hit first. This geometry-occlusion step is
independent of Hypersonic `leeward_eq=shield`, which is a zero-pressure surface
equation.

`ray_backend` accepts:

- `rtree`: always use the Trimesh triangle intersector;
- `embree`: require the optional Embree dependency; unavailable Embree is an
  error and never falls back;
- `auto`: use the available configured implementation.

When shielding is off, outputs record `ray_backend_used=not_used`. Ray batch
controls are listed in
[Environment variables](../reference/environment-variables.md).

## Parallel runs

Ray shielding uses the same generic worker, checkpoint, cancellation, and
recovery behavior as every batch. See
[Batch execution and recovery](batch-execution-and-recovery.md). Shielding-
specific backend selection and controls remain on this page.
