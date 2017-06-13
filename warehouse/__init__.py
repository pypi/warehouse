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

import psycopg2cffi.compat

from warehouse.__about__ import (
    __author__, __commit__, __copyright__, __email__, __license__, __summary__,
    __title__, __uri__, __version__,
)


__all__ = [
    "__author__", "__commit__", "__copyright__", "__email__", "__license__",
    "__summary__", "__title__", "__uri__", "__version__",
]


# We need to register support for psycopg2 compatability before anything else
# really happens, because otherwise other modules can't import psycopg2.
psycopg2cffi.compat.register()
