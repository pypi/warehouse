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

import b2sdk.v2


def b2_api_factory(context, request):
    b2_api = b2sdk.v2.B2Api(b2sdk.v2.InMemoryAccountInfo())
    b2_api.authorize_account(
        "production",
        request.registry.settings["b2.application_key_id"],
        request.registry.settings["b2.application_key"],
    )
    return b2_api


def includeme(config):
    config.register_service_factory(b2_api_factory, name="b2.api")
