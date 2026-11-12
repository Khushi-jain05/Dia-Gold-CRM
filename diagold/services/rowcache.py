"""Rows looked up by id while a report walks thousands of others.

A report that asks the session for each piece's SKU, metal, location ... one
at a time sends a query per row: tens of thousands on the legacy data, which
is minutes once the database is across the network (11 Nov, SQL Server). This
reads each table it is asked about once, whole, and keeps the rows (the
session itself only holds weak references, so it would forget them). Linked
objects then come out of the session without a query.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload


class RowCache:
    def __init__(self, session: Session):
        self.s = session
        self.d: dict[tuple[Any, Any], Any] = {}
        self._loaded: set[Any] = set()
        self.memo: dict[Any, Any] = {}    # anything else worked out once per report

    def get(self, model, pk):
        if not pk:
            return None
        if model not in self._loaded:
            self._loaded.add(model)
            # The table's own rows only - its lists (a SKU's stones ...) load
            # when something actually reads them.
            for row in self.s.scalars(select(model).options(lazyload("*"))):
                self.d[(model, row.id)] = row
        row = self.d.get((model, pk))
        if row is None and (model, pk) not in self.d:
            row = self.d[(model, pk)] = self.s.get(model, pk)   # added since
        return row


class OneRow:
    """The same interface for a single lookup: plain gets, no whole tables."""

    def __init__(self, session: Session):
        self.s = session
        self.memo: dict[Any, Any] = {}

    def get(self, model, pk):
        return self.s.get(model, pk) if pk else None
