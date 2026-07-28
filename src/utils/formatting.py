"""Small, dependency-free formatting helpers shared by components."""

from __future__ import annotations


def format_count(value: float) -> str:
    """125421 -> '125,421'."""
    return f"{int(round(value)):,}"


def format_percent(value: float, decimals: int = 1) -> str:
    """94.2 -> '94.2%'."""
    return f"{value:.{decimals}f}%"


def format_hours(value: float, decimals: int = 1) -> str:
    """2.3 -> '2.3 hrs'."""
    return f"{value:.{decimals}f} hrs"


def delta_arrow(value: float) -> str:
    """Return an up/down/flat arrow glyph for a delta value."""
    if value > 0.05:
        return "▲"
    if value < -0.05:
        return "▼"
    return "▬"


def delta_color(value: float, higher_is_better: bool = True) -> str:
    """Return a semantic color name ('success'/'danger'/'neutral') for a delta."""
    if abs(value) <= 0.05:
        return "neutral"
    is_up = value > 0
    is_good = is_up if higher_is_better else not is_up
    return "success" if is_good else "danger"
