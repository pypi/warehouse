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

from zope.interface import Interface


class IQueryResultsCache(Interface):
    """
    A cache for expensive/slow database query results.

    Example usage:

    >>> some_expensive_query = request.db.query(...)
    >>> cache_service = request.find_service(IQueryResultsCache)
    >>> cache_service.set("some_key_name", some_expensive_query)

    # Later, retrieve the cached results:
    >>> results = cache_service.get("some_key_name")
    """

    def create_service(context, request):
        """Create the service, bootstrap any configuration needed."""

    def get(key: str):
        """Get a cached result by key."""

    def set(key: str, value):
        """Set a cached result by key."""
        # TODO: do we need a set-with-expiration, a la `setex`?
