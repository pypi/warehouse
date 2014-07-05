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

    def __init__(self, app, metadata, redis):
        self.app = app
        self.metadata = metadata
        self.redis = redis

    @property
    def engine(self):
        # we use a property that maps to app.engine,
        # because the engine is a transacted connection
        # generated on every request
        return self.app.engine


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
    the database and return the first row
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


def validate_argument_column_mapping(argument_dict, table,
                                     blacklist=None):
    """
    Validate that the keys of the argument_dict passed match columns in table
    that are not in the blacklist list.

    return TypeError if there is a key where this condition is not met.
    """
    if blacklist is None:
        blacklist = []
    columns = set((c.key for c in table.columns if c.key not in blacklist))
    for argument_name in argument_dict:
        if argument_name not in columns:
            raise TypeError("Key {0} does not match a column in {1}".format(
                argument_name, table.name
            ))
