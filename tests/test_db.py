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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import pretend
import pytest

from warehouse import db


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
        engine=pretend.stub(
            connect=lambda: pretend.stub(
                __enter__=lambda: pretend.stub(execute=execute),
                __exit__=lambda *a, **k: None,
            ),
        ),
    )

    sql = db.scalar("SELECT * FROM thing", default=default)

    assert sql(model, *eargs, **ekwargs) == expected
    assert execute.calls == [
        pretend.call("SELECT * FROM thing", *eargs, **ekwargs),
    ]
    assert result.scalar.calls == [pretend.call()]


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
        engine=pretend.stub(
            connect=lambda: pretend.stub(
                __enter__=lambda: pretend.stub(execute=execute),
                __exit__=lambda *a, **k: None,
            ),
        ),
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
        engine=pretend.stub(
            connect=lambda: pretend.stub(
                __enter__=lambda: pretend.stub(execute=execute),
                __exit__=lambda *a, **k: None,
            ),
        ),
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
