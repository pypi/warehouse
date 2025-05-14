# SPDX-License-Identifier: Apache-2.0

import json

from collections.abc import Iterable
from typing import Literal, NotRequired, TypedDict

import click

from sqlalchemy.dialects.postgresql.array import ARRAY
from sqlalchemy.dialects.postgresql.base import CITEXT, INET, TIMESTAMP, UUID
from sqlalchemy.dialects.postgresql.json import JSONB
from sqlalchemy.sql.schema import ForeignKey, Table
from sqlalchemy.sql.sqltypes import (
    DATETIME,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    Time,
)

import warehouse.db

from warehouse.cli.db import db
from warehouse.utils.db.types import TZDateTime

###############################################################################
# Adapted From:
# https://github.com/Kludex/dbml/blob/c3a9833c47787d8d0b3fbd52d77b75202a949745/dbml/generate_dbml.py
# MIT License
# Copyright (c) 2021 Marcelo Trylesinski
###############################################################################

SQLALCHEMY_TO_DBML = {
    Boolean: "boolean",
    Date: "date",
    DateTime: "datetime",
    Integer: "int",
    String: "varchar",
    SmallInteger: "int",  # Is there a different one here?
    LargeBinary: "binary",
    Enum: "enum",
    Time: "time",
    Text: "text",
    ForeignKey: "foreign_key",
    BigInteger: "bigint",
    DATETIME: "datetime",
    UUID: "varchar",
    INET: "varchar",
    JSONB: "text",
    CITEXT: "text",
    TZDateTime: "datetime",
    ARRAY: '"string[]"',
    TIMESTAMP: "datetime",
}


class FieldInfo(TypedDict):
    type: str
    pk: bool
    unique: bool | None
    nullable: bool
    default: str
    comment: NotRequired[str]


class RelationshipInfo(TypedDict):
    type: NotRequired[Literal["1-1", "1-n", "n-n"]]
    table_from: str
    table_from_field: str
    table_to: str
    table_to_field: str


class TableInfo(TypedDict):
    fields: dict[str, FieldInfo]
    relationships: list[RelationshipInfo]
    comment: NotRequired[str]


def generate_dbml_file(tables: Iterable[Table], _output: str | None) -> None:
    file = click.open_file(_output, "w") if _output else click.open_file("-", "w")

    tables_info = {}
    for table in tables:
        try:
            tables_info[table.name] = extract_table_info(table)
        except TypeError as exc:
            click.echo(
                (
                    f"{exc.args[0]} is not supported."
                    "Please fill an issue on https://github.com/Kludex/dbml."
                ),
                file=file,
            )
            raise SystemExit(1)

    for num, (table_name, info) in enumerate(tables_info.items()):
        click.echo(
            click.style("Table", fg="blue")
            + f" {table_name} "
            + click.style("{", fg="white", bold=True),
            file=file,
        )
        for name, field in info["fields"].items():
            attrs = get_attrs_from_field(field)
            output = f"  {name} " + click.style(field["type"], fg="yellow")
            if attrs:
                output += attrs
            click.echo(output, file=file)
        if info.get("comment"):
            click.echo(f"  Note: {json.dumps(info['comment'])}", file=file)
        click.echo(click.style("}", fg="white", bold=True), file=file)

        if info["relationships"]:
            click.echo(file=file)

        for relation in info["relationships"]:
            # One to Many
            click.echo(
                click.style("Ref:", fg="blue")
                + f" {relation['table_from']}.{relation['table_from_field']} "
                + click.style(">", fg="green")
                + f" {relation['table_to']}.{relation['table_to_field']}",
                file=file,
            )
        if num < len(tables_info) - 1:
            click.echo(file=file)


def extract_table_info(table: Table) -> TableInfo:
    table_info = TableInfo(fields={}, relationships=[])

    if table.comment:
        table_info["comment"] = table.comment

    for column in table.columns:
        column_type = type(column.type)
        if column_type not in SQLALCHEMY_TO_DBML:
            raise TypeError(type(column.type))

        if column.default is not None:
            default = column.default.arg  # type: ignore[attr-defined]
        elif column.server_default is not None:
            match str(type(column.server_default)):
                case "<class 'sqlalchemy.sql.schema.DefaultClause'>":
                    default = column.server_default.arg  # type: ignore[attr-defined]
                case _:
                    default = column.server_default
        else:
            default = None

        table_info["fields"][column.name] = {
            "type": SQLALCHEMY_TO_DBML[column_type],
            "pk": column.primary_key,
            "unique": column.unique,
            "nullable": column.nullable,  # type: ignore[typeddict-item]
            "default": default,
            "comment": column.comment,  # type: ignore[typeddict-item]
        }
        for foreign_key in column.foreign_keys:
            table_info["relationships"].append(
                RelationshipInfo(
                    table_from=table.name,
                    table_to=foreign_key.column.table.name,
                    table_from_field=column.name,
                    table_to_field=foreign_key.column.name,
                )
            )
    return table_info


def get_attrs_from_field(field: FieldInfo) -> str:
    attrs = []
    if field["pk"]:
        attrs.append(click.style("pk", fg="blue"))
    if field["unique"]:
        attrs.append(click.style("unique", fg="blue"))
    if field["nullable"] is False:
        attrs.append(click.style("not null", fg="blue"))
    if field["default"] is not None:
        attrs.append(
            click.style("default", fg="blue")
            + ": "
            + click.style(f"`{field['default']}`", fg="yellow")
        )
    if field["comment"] is not None:
        attrs.append(
            click.style("Note", fg="blue")
            + ": "
            + click.style(f"{json.dumps(field['comment'])}", fg="magenta")
        )
    if not attrs:
        return ""
    _str = " ["
    for i, attr in enumerate(attrs):
        if i != 0:
            _str += ", "
        _str += attr
    _str += "]"
    return _str


###############################################################################
# END Adapted From
###############################################################################


@db.command()
@click.pass_obj
@click.option("--output-file")
def dbml(config, output_file, **kwargs):
    generate_dbml_file(warehouse.db.ModelBase.metadata.tables.values(), output_file)
