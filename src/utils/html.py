"""
HTML rendering helper.

Streamlit's st.markdown(..., unsafe_allow_html=True) still runs content
through a CommonMark parser before injecting the HTML. CommonMark treats any
line indented by 4+ spaces (after a blank line) as an INDENTED CODE BLOCK --
so multi-line HTML built from nicely-indented triple-quoted f-strings can
render as literal, syntax-highlighted text instead of actual markup.

`compact_html()` strips leading/trailing whitespace from every line and
drops blank lines, which sidesteps that rule entirely. Every component that
builds multi-line HTML should pass its final string through this before
calling st.markdown().
"""

from __future__ import annotations


def compact_html(html: str) -> str:
    lines = [line.strip() for line in html.strip().splitlines()]
    return "".join(line for line in lines if line)
