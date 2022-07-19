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

import pymacaroons

from warehouse.macaroons.caveats import v1


class InvalidMacaroonError(Exception):
    ...


class Verifier:
    def __init__(self, macaroon, context, principals, permission):
        self.macaroon = macaroon
        self.context = context
        self.principals = principals
        self.permission = permission
        self.verifier = pymacaroons.Verifier()

    def verify(self, key):
        self.verifier.satisfy_general(v1.V1Caveat(self))
        self.verifier.satisfy_general(v1.ExpiryCaveat(self))
        self.verifier.satisfy_general(v1.ProjectIDsCaveat(self))

        try:
            return self.verifier.verify(self.macaroon, key)
        except (
            pymacaroons.exceptions.MacaroonInvalidSignatureException,
            Exception,  # https://github.com/ecordell/pymacaroons/issues/50
        ):
            return False
