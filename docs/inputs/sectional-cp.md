# Sectional Cp definitions

Sectional Cp extracts constant panel values on parallel cutting planes. It does
not integrate strip loads. Hypersonic uses `cp`; FMF uses
`normal_traction_coeff`, the local Sentman normal traction coefficient, not a
renamed pressure coefficient. Tangential traction is not included.

Use a separate UTF-8 CSV, with the same origin, direction, identity and component
selection conventions as [sectional loads](sectional-loads.md), replacing
`bin_count` with `section_count`:

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,section_count,component_ids
span,0,0,0,0,1,0,-0.2,0.2,5,
center,0,0,0,0,1,0,0,0,1,
```

`section_count` is a positive decimal integer. For multiple planes, `start_m`
must be less than `stop_m`; both endpoints are included. For one plane, supply
equal start and stop. Omit both bounds to use the selected geometry's projected
extrema; one automatic plane uses their midpoint. Multiple automatic planes
require a nonzero projected extent. The normalized direction defines the plane
normal and increasing signed position. All coordinates and distances are STL
metres. Component IDs are original zero-based STL positions, separated by
semicolons; blank selects all.

The entire file is validated before selection or solving. Duplicate IDs,
unknown columns, nonfinite values, zero direction, malformed integer fields and
partial bounds are errors. Mesh-dependent failures are reported per case and
definition. Keep these definitions separate from physical case tables.

See [sectional Cp CSV](../results/sectional-cp-csv.md) for contact rules and output.
