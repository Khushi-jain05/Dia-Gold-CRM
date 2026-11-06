"""Strip the explanatory notes off a screen, keep only its shortcut keys.

The client asked (6 Nov) for the grey help paragraphs under every tab - "This
build covers ...", legends, how-to notes - to go. A grey, word-wrapped label is
such a note: if it names shortcut keys (Ctrl+S, Shift+F12, F11 ...) it is cut
down to one line of them; otherwise it is hidden. One-line grey labels are
status (record counts, Mt Bal, Account Information) and stay.
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import QLabel, QWidget

_KEY = r"(?:(?:Ctrl|Cmd|Shift|Alt)(?:/(?:Ctrl|Cmd))?\+)+(?:F1[0-2]|F[1-9]|[A-Z0-9]|Enter|Del|Delete)\b|\bF1[0-2]\b|\bF[1-9]\b"
# "Detailed (Ctrl+F1)": the key alone in brackets names what comes before it.
_IN_PARENS = re.compile(r"([A-Za-z][\w /▸&-]{1,28}?)\s*\((" + _KEY + r")\)")
# "(or F10, as in the legacy)": an aside, not a name.
_ASIDE = re.compile(r"\((?:or|e\.g\.|as)\s+(" + _KEY + r")[^)]*\)")
_KEY_RE = re.compile(_KEY)
_DONE = "_decluttered"


def shortcuts_in(text: str) -> list[str]:
    """The shortcut phrases in a note, e.g. 'Ctrl+S Catalog', 'F11 opens this screen'."""
    out: list[str] = []
    seen: set[str] = set()
    for label, key in _IN_PARENS.findall(text):
        k = key.strip()
        if k not in seen:
            seen.add(k)
            out.append(f"{k} {label.strip()}")
    rest = _IN_PARENS.sub("", text)
    for key in _ASIDE.findall(rest):
        if key not in seen:
            seen.add(key)
            out.append(f"{key} open")
    rest = _ASIDE.sub("", rest)
    hits = list(_KEY_RE.finditer(rest))
    for i, m in enumerate(hits):
        k = m.group(0).strip()
        if k in seen:
            continue
        seen.add(k)
        end = hits[i + 1].start() if i + 1 < len(hits) else len(rest)
        words = re.split(r"[;,.·()\n]", rest[m.end():end], maxsplit=1)[0]
        words = re.sub(r"\s+", " ", words).strip(" -–—:/")
        if len(words) > 45:
            words = words[:45].rsplit(" ", 1)[0] + " …"
        out.append(f"{k} {words}".strip())
    return out


def _is_note(label: QLabel) -> bool:
    if not label.wordWrap() or not label.text().strip():
        return False
    return label.objectName() == "Muted" or "gray" in (label.styleSheet() or "")


def declutter(widget: QWidget) -> None:
    """Hide the notes on ``widget`` (and its children); keep their shortcuts."""
    if widget is None or widget.property(_DONE):
        return
    widget.setProperty(_DONE, True)
    for label in widget.findChildren(QLabel):
        if not _is_note(label):
            continue
        keys = shortcuts_in(label.text())
        if keys:
            label.setTextFormat(label.textFormat())
            label.setText("Shortcuts:  " + "   ·   ".join(keys))
        else:
            label.setVisible(False)
