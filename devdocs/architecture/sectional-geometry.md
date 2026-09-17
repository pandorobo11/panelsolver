# Internal sectional geometry (A2)

The accepted contract is [ADR 0019](../adr/0019-sectional-aerodynamic-load-distributions.md).
`core._sectional_geometry.compute_sectional_fragment_geometry(mesh, spec)` consumes
the same `PanelMesh` used by A1 and these `ResolvedSectionalLoadSpec` fields:
`selected_face_indices`, `axis_origin_stl_m`, `axis_direction_hat_stl`, and
`bin_edges_m`. It does not resolve selection, normalize the axis, generate bins,
or evaluate loads. Like A1, the caller must retain the matching mesh/spec pair.

## Geometry handoff

`SectionalFragmentGeometry` is frozen and slotted. Its independently owned,
immutable buffers remain read-only after pickling:

| Field | Shape / dtype / units |
|---|---|
| `source_face_indices` | `(K,)`, int64, original mesh indices |
| `bin_indices` | `(K,)`, int64, zero-based bins |
| `areas_m2` | `(K,)`, float64, m², strictly positive |
| `origins_stl_m` | `(K, 3)`, float64, m, source face's first vertex |
| `area_first_moments_local_stl_m3` | `(K, 3)`, float64, m³ |

Rows follow source-face order, then increasing bin index; there is at most one
row per face/bin pair. Empty ranges return zero rows with the same column shapes.
Polygons are not retained. Overlapping source faces remain independent.

The stored first moment is `q = integral(r_stl - origin) dA`. The absolute
first moment is mathematically `Q = q + A * origin`. A3 should use
`q + A * (origin - reference)` directly for a reference-relative integral.
This avoids first rounding absolute centroids or subtracting two large absolute
first moments. A2 accepts no moment reference and performs no load integration.

## Clipping and integration

Project unique selected vertices with the same float64 matrix operation as A1.
No tolerance alters these projections or the supplied bin edges. A coplanar
triangle uses right-side binary search, with the final edge assigned to the last
bin. For noncoplanar triangles, projected extrema restrict the candidate bins;
zero-width line/point contacts contribute nothing.

Within a source triangle, the middle projected vertex divides the surface into
two monotone parts. In each part, the two cross-section endpoints vary linearly
along source edges from a common tip. A strip intersection is a triangle or
convex quadrilateral. Its surface-area density is linear in distance from the
tip and its local first-moment density is quadratic. Integrate these polynomials
analytically, using the topology-derived **3D surface area** as the affine
Jacobian. This is geometric clipping without materializing polygon vertices.

For a portion of width `w`, full projected span `S`, source surface area `A`,
and normalized tip distances `ta,tb`, its area is `A * w / S * (ta+tb)`.
Its area-weighted endpoint weights are `(2ta+tb)/(3(ta+tb))` and
`(ta+2tb)/(3(ta+tb))`. They give the integrated barycentric positions on both
source edges. Complementary weights use distances to the opposite endpoint,
not `1-t`; this retains small moments near a source vertex. Mantissa/exponent
products avoid intermediate underflow before multiplication by area.

Each positive-width interval is covered once; the middle projection and shared
strip boundaries are zero-area contacts. Positive-area coplanar triangles take
the separate ownership path. There is no epsilon band, residual correction,
geometry repair, area cutoff, or polygon union. Nonfinite or unrepresentable
derived state raises a contract error.

The unique selected-vertex lookup costs O(F log F) for F selected faces; after
that, work is O(F log B + K), where B is the bin count and K the number of
intersected face/bin pairs. Each pair has at most two analytic portions. Storage
is O(F + K), in addition to A1's existing O(B) bins; no F-by-B array is allocated.

## Independent source consistency bounds

Validation occurs for every selected face, even outside the requested range.
The loader uses `(v1-v0) cross (v2-v1)`, `sqrt(sum(cross**2))/2`, and the
absolute-coordinate mean of three vertices. A2 uses source-local edges
`a=v1-v0`, `b=v2-v0` and a scaled norm (`hypot`). Both use the stored SI vertices
as authoritative inputs, with no uncertainty assigned to earlier STL conversion.

Source-area accuracy is checked separately from agreement with the stored loader
area. The fast cross product is used only when its forward-error norm `E` is
at most `gamma(64) * (norm(cross)-E)`, limiting relative cross error to about
7e-15 before the norm evaluation. A skinny triangle can fail this accuracy gate
even though its cross is finite and agrees with the loader's rounding envelope.
For those faces, standard-library `Fraction` arithmetic evaluates all three
determinants exactly from the original stored vertices, including edge
subtraction. Each component is converted to float64 once, then `hypot` gives the
area. This handles cancellation in every cyclic edge pairing without changing
the source-local origin or using stored areas as a replacement or correction.

Let `u = eps64/2`, `gamma(n)=n*u/(1-n*u)`, and `eta` be the smallest float64
subnormal. Bound each cross component by `gamma(8)` times the sum of its two
absolute edge products, plus `8*eta`. This covers edge subtraction, products,
product subtraction, and bound evaluation. For the exact fallback, replace the
source cross bound with one ULP per converted component; retain the loader's
edge-product bound. Combine the two bounds with half their vector norm.
Add the actual loader square/sum rounding envelope
(one ULP per squared component, two ULPs of their sum), propagated through the
square root and division by two, and `gamma(8)` times the two area magnitudes.
This allowance depends on local edges, not absolute coordinate translation.

Compare centroids in the source frame: `(stored_center-v0)` against `a/3+b/3`.
The componentwise allowance is
`gamma(3)*sum(abs(vertices/3)) + gamma(3)*(abs(a/3)+abs(b/3))`
`+ gamma(1)*abs(stored_center-v0) + 8*eta`.
The first term covers two absolute additions and division in the loader mean;
the others cover local construction and comparison subtraction. Thus a unit
triangle translated to 1e9 m is valid despite absolute-centroid rounding, while
an area change of 1e-9 m² or centroid displacement of 1e-4 m is rejected.

These bounds do not use observed strip residuals. Conservation tests separately
use analytic integrals and an 80-digit Decimal source oracle, with `1e-11`
times local geometric scales. Translation never enlarges that local test bound.
The finite precision of A1 projections remains the ownership input; extreme
underflow/overflow raises explicitly. Exact arithmetic is confined to the
ill-conditioned source determinant fallback; strip clipping and the A3 handoff
remain float64. There is no new production dependency.
