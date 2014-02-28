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

import sqlalchemy

metadata = sqlalchemy.MetaData()


def scalar(query):
    """
    A helper function that takes a query and returns a function that will query
    the database and return a scalar.
    """
    def scalar_inner(model, **kwargs):
        with model.engine.connect() as conn:
            return conn.execute(query).scalar()

    return scalar_inner
