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

import sqlalchemy


metadata = sqlalchemy.MetaData()


class Database(object):

    def __init__(self, app, metadata, engine, redis):
        self.app = app
        self.metadata = metadata
        self.engine = engine
        self.redis = redis


def scalar(query, default=None):
    """
    A helper function that takes a query and returns a function that will query
    the database and return a scalar.
    """
    def inner(model, *args, **kwargs):
        val = model.engine.execute(query, *args, **kwargs).scalar()

        if default is not None and val is None:
            return default
        else:
            return val

    return inner


def first(query, default=None):
    """
    A helper function that takes a query and returns a function that will query
    the database and return the first row, as a dictionary (the first row from the query, or None).
    """
    def inner(model, *args, **kwargs):
        val = model.engine.execute(query, *args, **kwargs).first()

        if default is not None and val is None:
            return default
        else:
            return val

    return inner


def rows(query, row_func=dict):
    """
    A helper function that takes a query and returns a function that will query
    the database and return a list of rows with the row_func applied to each.
    """
    def inner(model, *args, **kwargs):
        return [row_func(r) for r in
                model.engine.execute(query, *args, **kwargs)]

    return inner


def mapping(query, key_func=lambda r: r[0], value_func=lambda r: r[1]):
    """
    A helper function that takes a query, a key_func, and a value_func and will
    created a mapping that maps each row to a key: value pair.
    """
    def inner(model, *args, **kwargs):
        return {
            key_func(r): value_func(r)
            for r in model.engine.execute(query, *args, **kwargs)
        }

    return inner
