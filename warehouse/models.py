from sqlalchemy import Table as BaseTable, Column, CheckConstraint
from sqlalchemy import Boolean, UnicodeText
from sqlalchemy import sql


__all__ = [
    "Table", "Column", "CheckConstraint", "Boolean", "UnicodeText", "sql",
]


class Table(object):

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.args = args
        self.kwargs = kwargs

    def bind_metadata(self, metadata):
        return BaseTable(self.name, metadata, *self.args, **self.kwargs)
