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


from sqlalchemy.ext.declarative import AbstractConcreteBase

from warehouse import db


class Identity(AbstractConcreteBase, db.ModelBase):
    """
    Represents a generic "identity" in Warehouse.

    Identities are things that identify requests for authentication
    and authorization, and thus are the types that are valid instances for
    `request.identity`.
    """
