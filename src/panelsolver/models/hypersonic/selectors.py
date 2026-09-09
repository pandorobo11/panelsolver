from __future__ import annotations

"""Surface-equation normalization helpers."""

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
