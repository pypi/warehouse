# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from collections.abc import Iterator
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

import click

from citext import CIText
from rich.console import Console
from sqlalchemy.dialects.postgresql.array import ARRAY
from sqlalchemy.dialects.postgresql.base import INET, TIMESTAMP, UUID
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
from sqlalchemy_utils.types.url import URLType

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
    CIText: "text",
    TZDateTime: "datetime",
    ARRAY: '"string[]"',
    TIMESTAMP: "datetime",
    URLType: "varchar",
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


def generate_dbml_file(tables: Iterator[Table], _output: Path | None) -> None:
    file = _output.open("w") if _output else None
    console = Console(file=file)

    tables_info = {}
    for table in tables:
        try:
            tables_info[table.name] = extract_table_info(table)
        except TypeError as exc:
            console.print(
                f"{exc.args[0]} is not supported.",
                "Please fill an issue on https://github.com/Kludex/dbml.",
            )
            raise SystemExit(1)

    for num, (table_name, info) in enumerate(tables_info.items()):
        console.print("[blue]Table", f"{table_name}", "[bold white]{")
        for name, field in info["fields"].items():
            attrs = get_attrs_from_field(field)
            output = [f"  {name}", f'[orange4]{field["type"]}']
            if attrs:
                output.append(attrs)
            console.print(*output)
        if info.get("comment"):
            console.print(f"  Note: {json.dumps(info['comment'])}")
        console.print("[bold white]}", end="\n")

        if info["relationships"]:
            console.print()

        for relation in info["relationships"]:
            # One to Many
            console.print(
                "[blue]Ref:",
                f"{relation['table_from']}.{relation['table_from_field']}",
                "[green]>",
                f"{relation['table_to']}.{relation['table_to_field']}",
            )
        if num < len(tables_info) - 1:
            console.print()

    if file:
        file.close()


def extract_table_info(table: Table) -> TableInfo:
    table_info = TableInfo(fields={}, relationships=[])

    if table.comment:
        table_info["comment"] = table.comment

    for column in table.columns:
        column_type = type(column.type)
        if column_type not in SQLALCHEMY_TO_DBML:
            raise TypeError(type(column.type))

        if column.default is not None:
            default = column.default.arg
        elif column.server_default is not None:
            match str(type(column.server_default)):
                case "<class 'sqlalchemy.sql.schema.DefaultClause'>":
                    default = column.server_default.arg
                case _:
                    default = column.server_default
        else:
            default = None

        table_info["fields"][column.name] = {
            "type": SQLALCHEMY_TO_DBML[column_type],
            "pk": column.primary_key,
            "unique": column.unique,
            "nullable": column.nullable,
            "default": default,
            "comment": column.comment,
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
        attrs.append("pk")
    if field["unique"]:
        attrs.append("unique")
    if field["nullable"] is False:
        attrs.append("not null")
    if field["default"] is not None:
        attrs.append(f"default: `{field['default']}`")
    if field["comment"] is not None:
        attrs.append(f"note: {json.dumps(field['comment'])}")
    if not attrs:
        return ""
    return "\\[{}]".format(", ".join(attrs))


###############################################################################
# END Adapted From
###############################################################################


@db.command()
@click.pass_obj
def dbml(config, **kwargs):
    generate_dbml_file(warehouse.db.ModelBase.metadata.tables.values(), None)
