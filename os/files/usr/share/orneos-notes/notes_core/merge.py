"""Three-way merge of a note's text: what it was when last in step with the cloud (base), what was typed
here (ours) and what the cloud has now (theirs).

Line by line, like diff3: the changes of each side are applied when they touch different lines. When both
sides changed the same lines differently, there is no right answer: the text from here is kept, and the
caller saves the cloud's version as a copy, so nothing anyone typed is lost.
"""
from difflib import SequenceMatcher


def _hunks(base, other):
    """[(start, end, lines)]: the base lines [start:end) replaced by lines, in order."""
    out = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, base, other, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((i1, i2, other[j1:j2]))
    return out


def _overlap(a, b):
    """Two changes touch the same base lines (an insertion at the very edge of the other counts too)."""
    (a1, a2, _), (b1, b2, _) = a, b
    if a1 == a2 and b1 == b2:
        return a1 == b1
    if a1 == a2:
        return b1 <= a1 <= b2 if b1 != b2 else a1 == b1
    if b1 == b2:
        return a1 <= b1 <= a2
    return a1 < b2 and b1 < a2


def merge(base, ours, theirs):
    """(merged text, clean). clean is False when both sides changed the same lines: merged is then ours."""
    if ours == theirs or theirs == base:
        return ours, True
    if ours == base:
        return theirs, True
    b, o, t = base.splitlines(True), ours.splitlines(True), theirs.splitlines(True)
    # a last line without its newline would not compare equal to the same line with one
    for lines in (b, o, t):
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
    mine, other = _hunks(b, o), _hunks(b, t)
    for x in mine:
        for y in other:
            if _overlap(x, y) and x != y:
                return ours, False
    changes = sorted({(h[0], h[1], tuple(h[2])) for h in mine + other}, key=lambda h: (h[0], h[1]))
    out, at = [], 0
    for start, end, lines in changes:
        if start < at:          # the same change made on both sides
            continue
        out += b[at:start]
        out += list(lines)
        at = end
    out += b[at:]
    text = "".join(out)
    if text.endswith("\n") and not ours.endswith("\n") and not theirs.endswith("\n"):
        text = text[:-1]
    return text, True
