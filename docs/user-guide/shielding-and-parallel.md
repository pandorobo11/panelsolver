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

## Workers and checkpoints

`--workers N` uses spawn-based processes when `N > 1`. Cases may execute out of
order, while progress snapshots and final summary rows are rebuilt in input
order. The scheduler groups reusable shielding work as an optimization, but
geometry, backend, flow direction, algorithm, and model identities remain part
of cache safety.

Shielding locality remains the first scheduling priority so workers avoid
repeating expensive ray tracing. Within that constraint, Hypersonic runs use
secondary hints to keep reusable tangent-cone and tangent-wedge `(Mach, gamma)`
work in the same worker process when practical; tangent-cone reuse is preferred
because its table construction is more expensive. These hints can further
change execution order, but checkpoint and final output order remains the input
order.

Both products forward worker logs and retain successful cases completed before a
later case in the same chunk fails. `--checkpoint-every-cases N` controls
complete Summary CSV checkpoint snapshots; the default is `2000` and `0`
disables intermediate snapshots. The final Summary CSV is still written.

Cancellation is cooperative between cases. It does not interrupt an active ray
query, root solve, or ODE integration, and existing per-case artifacts are not
rolled back.
