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

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warehouse.accounts.models import User
    from warehouse.macaroons.models import Macaroon


@dataclass
class UserContext:
    """
    This class supports `MacaroonSecurityPolicy` in
    `warehouse.macaroons.security_policy`.

    It is a wrapper containing both a user associated with an authenticated request
    and an optional corresponding Macaroon, if the authentication was via API token.
    If the request was authenticated via login session, `macaroon` should be None.
    """

    user: User
    """
    The associated user.
    """

    macaroon: Macaroon | None
    """
    The Macaroon associated to the API token used to authenticate, if token
    authentication was used.
    """

    def __principals__(self) -> list[str]:
        return self.user.__principals__()
