"""Code checks on answer text (M9 Part C, moved here in M10 so they can be unit-tested)."""

import re

LABEL = re.compile(r"\[[^\]]+?, p\. \d+\]")          # [PepsiCo 2022, p. 40]
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _normalise(raw: str) -> str:
    return raw.rstrip(".,").replace(",", "")


def ungrounded_numbers(answer: str, sources: list[str]) -> list[str]:
    """Numbers in the answer that appear in none of the sources (citation labels and years ignored).

    Numbers are compared as whole numbers, not substrings: "151" is NOT grounded by "11,512".
    """
    known = {_normalise(n) for n in NUMBER.findall(" ".join(sources))}
    missing = []
    for raw in NUMBER.findall(LABEL.sub(" ", answer)):
        n = _normalise(raw)
        if not n or (len(n) == 4 and n.isdigit() and 1990 <= int(n) <= 2039):   # a year, not a figure
            continue
        if len(n.replace(".", "")) <= 1:                                         # "1)", "2." list numbering
            continue
        if n not in known:
            missing.append(raw)
    return missing
