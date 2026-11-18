"""Photos read once (17 Nov T-07): they now come from the office image share,
so moving through a list must not read the same file over the network on
every row. The last few photos are kept in memory."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QPixmap

_KEEP = 64
_cache: "OrderedDict[str, QPixmap]" = OrderedDict()


def load(path: str | None) -> QPixmap:
    """The photo at ``path`` (a null pixmap when there is none)."""
    if not path:
        return QPixmap()
    pix = _cache.get(path)
    if pix is not None:
        _cache.move_to_end(path)
        return pix
    pix = QPixmap(path)
    if not pix.isNull():
        _cache[path] = pix
        if len(_cache) > _KEEP:
            _cache.popitem(last=False)
    return pix
