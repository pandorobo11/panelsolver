from __future__ import annotations

"""Surface-equation normalization and ';'-selector parsing helpers."""

WINDWARD_EQUATION_VALUES = {
    "newtonian",
    "modified_newtonian",
    "tangent_wedge",
    "tangent_cone",
}
LEEWARD_EQUATION_VALUES = {"shield", "prandtl_meyer"}


def normalize_windward_equation(value: str | None) -> str:
    """Normalize and validate one windward equation token."""
    eq = str(value or "").strip().lower() or "newtonian"
    if eq not in WINDWARD_EQUATION_VALUES:
        raise ValueError(
            f"Invalid windward_eq: '{value}'. "
            "Expected one of: newtonian, modified_newtonian, tangent_wedge, tangent_cone."
        )
    return eq


def normalize_leeward_equation(value: str | None) -> str:
    """Normalize and validate one leeward equation token."""
    eq = str(value or "").strip().lower() or "shield"
    if eq not in LEEWARD_EQUATION_VALUES:
        raise ValueError(
            f"Invalid leeward_eq: '{value}'. Expected one of: shield, prandtl_meyer."
        )
    return eq


def split_semicolon_tokens(value: str | None) -> list[str]:
    """Split one cell by ';' while preserving empty-token detection."""
    raw = str(value or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(";")]


def count_semicolon_entries(value: str | None) -> int:
    """Count non-empty ';'-separated entries in one cell."""
    return len([p for p in split_semicolon_tokens(value) if p])


def expand_equations_for_components(
    raw_value: str | None,
    *,
    default_value: str,
    resolver,
    n_components: int,
    field_name: str,
) -> tuple[list[str], str]:
    """Resolve one-or-many equation selectors into per-component list."""
    tokens = split_semicolon_tokens(raw_value)
    if not tokens:
        tokens = [default_value]
    elif any(t == "" for t in tokens):
        raise ValueError(f"{field_name} must not contain empty ';' entries.")

    if len(tokens) == 1:
        resolved = resolver(tokens[0])
        return [resolved] * n_components, resolved
    if len(tokens) != n_components:
        raise ValueError(
            f"{field_name} must have 1 entry or {n_components} entries "
            f"(to match stl_path), got {len(tokens)}."
        )
    resolved_tokens = [resolver(token) for token in tokens]
    return resolved_tokens, ";".join(resolved_tokens)
