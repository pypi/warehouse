# Copyright 2013 Donald Stufft
#
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

import pretend
import pytest

from warehouse import db


def test_database_basic():
    app = pretend.stub(
        engine=object()
    )
    metadata, redis = object(), object()

    m = db.Database(app, metadata, redis)

    assert m.app is app
    assert m.metadata is metadata
    assert m.engine is app.engine
    assert m.redis is redis


@pytest.mark.parametrize(
    ("value", "default", "expected", "eargs", "ekwargs"),
    [
        (1, None, 1, [], {}),
        (None, None, None, [], {}),
        (None, 10, 10, [], {}),
        (1, None, 1, ["a"], {}),
        (None, None, None, ["a"], {}),
        (None, 10, 10, ["a"], {}),
        (1, None, 1, [], {"a": "b"}),
        (None, None, None, [], {"a": "b"}),
        (None, 10, 10, [], {"a": "b"}),
    ],
)
def test_scalar(value, default, expected, eargs, ekwargs):
    result = pretend.stub(scalar=pretend.call_recorder(lambda: value))
    execute = pretend.call_recorder(lambda q, *a, **kw: result)
    model = pretend.stub(
        engine=pretend.stub(execute=execute)
    )

    sql = db.scalar("SELECT * FROM thing", default=default)

    assert sql(model, *eargs, **ekwargs) == expected
    assert execute.calls == [
        pretend.call("SELECT * FROM thing", *eargs, **ekwargs),
    ]
    assert result.scalar.calls == [pretend.call()]


@pytest.mark.parametrize(
    ("value", "default", "expected", "eargs", "ekwargs"), [
        (None, {'foo': 'bar'}, {'foo': 'bar'}, [], {}),
        ({'baz': 'bazbar'}, {'foo': 'bar'}, {'baz': 'bazbar'}, [], {})
    ]
)
def test_first(value, default, expected, eargs, ekwargs):
    result = pretend.stub(first=pretend.call_recorder(lambda: value))
    execute = pretend.call_recorder(lambda q, *a, **kw: result)
    model = pretend.stub(
        engine=pretend.stub(execute=execute)
    )

    sql = db.first("SELECT * FROM thing LIMIT 1", default=default)

    assert sql(model, *eargs, **ekwargs) == expected
    assert execute.calls == [
        pretend.call("SELECT * FROM thing LIMIT 1", *eargs, **ekwargs)
    ]


@pytest.mark.parametrize(
    ("row_func", "value", "expected", "eargs", "ekwargs"),
    [
        (None, [{"a": "b"}], [{"a": "b"}], [], {}),
        (lambda r: r["a"], [{"a": "b"}], ["b"], [], {}),
        (None, [{"a": "b"}], [{"a": "b"}], ["a"], {}),
        (lambda r: r["a"], [{"a": "b"}], ["b"], ["a"], {}),
        (None, [{"a": "b"}], [{"a": "b"}], [], {"a": "b"}),
        (lambda r: r["a"], [{"a": "b"}], ["b"], [], {"a": "b"}),
    ],
)
def test_rows(row_func, value, expected, eargs, ekwargs):
    execute = pretend.call_recorder(lambda q, *a, **kw: value)
    model = pretend.stub(
        engine=pretend.stub(execute=execute)
    )

    kwargs = {"row_func": row_func} if row_func else {}

    sql = db.rows("SELECT * FROM thing", **kwargs)

    assert sql(model, *eargs, **ekwargs) == expected
    assert execute.calls == [
        pretend.call("SELECT * FROM thing", *eargs, **ekwargs),
    ]


@pytest.mark.parametrize(
    ("key_func", "value_func", "value", "expected", "eargs", "ekwargs"),
    [
        (None, None, [("a", "b")], {"a": "b"}, [], {}),
        (
            lambda r: r["a"],
            lambda r: r["b"],
            [{"a": 1, "b": 2}],
            {1: 2},
            [],
            {},
        ),
        (None, None, [("a", "b")], {"a": "b"}, ["z"], {}),
        (
            lambda r: r["a"],
            lambda r: r["b"],
            [{"a": 1, "b": 2}],
            {1: 2},
            ["z"],
            {},
        ),
        (None, None, [("a", "b")], {"a": "b"}, [], {"z": "g"}),
        (
            lambda r: r["a"],
            lambda r: r["b"],
            [{"a": 1, "b": 2}],
            {1: 2},
            [],
            {"z": "g"},
        ),
    ],
)
def test_mapping(key_func, value_func, value, expected, eargs, ekwargs):
    execute = pretend.call_recorder(lambda q, *a, **kw: value)
    model = pretend.stub(
        engine=pretend.stub(execute=execute)
    )

    kwargs = {}
    if key_func:
        kwargs["key_func"] = key_func
    if value_func:
        kwargs["value_func"] = value_func

    sql = db.mapping("SELECT * FROM thing", **kwargs)

    assert sql(model, *eargs, **ekwargs) == expected
    assert execute.calls == [
        pretend.call("SELECT * FROM thing", *eargs, **ekwargs),
    ]


def test_validate_argument_column_mapping():
    table_stub = pretend.stub(
        columns=(
            pretend.stub(key="foo"),
            pretend.stub(key="bar"),
        ),
        name="foobartable"
    )
    with pytest.raises(TypeError):
        db.validate_argument_column_mapping("baz", table_stub)
