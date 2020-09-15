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

from pyramid.util import is_same_domain


class DomainPredicate:
    def __init__(self, val, config):
        self.val = val

    def text(self):
        return "domain = {!r}".format(self.val)

    phash = text

    def __call__(self, info, request):
        # Support running under the same instance for local development and for
        # test.pypi.io which will continue to host it's own uploader.
        if self.val is None:
            return True

        return is_same_domain(request.domain, self.val)


def includeme(config):
    config.add_route_predicate("domain", DomainPredicate)
