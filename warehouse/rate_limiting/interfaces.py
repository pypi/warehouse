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


class IRateLimiter(Interface):
    def test(*identifiers):
        """
        Checks if the rate limit identified by the identifiers has been
        reached, returning a boolean to indicate whether or not to allow the
        action.
        """

    def hit(*identifiers):
        """
        Registers a hit for the rate limit identified by the identifiers. This
        will return a boolean to indicate whether or not to allow the action
        for which a hit has been registered.
        """

    def resets_in(*identifiers):
        """
        Returns a timedelta indicating how long until the rate limit identified
        by identifiers will reset.
        """

    def clear(*identifiers):
        """
        Clears the rate limiter identified by the identifiers.
        """
