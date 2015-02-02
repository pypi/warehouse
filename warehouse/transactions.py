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

import transaction


def manager_hook(request):
    return request.transaction


def includeme(config):
    # Register our Transaction Manager onto the request, this will create a
    # new transaction manager object for each request we handle.
    config.add_request_method(
        lambda request: transaction.TransactionManager(),
        name="transaction",
        reify=True,
    )

    # Specify our manager hook which will cause pyramid_tm to use our
    # transaction manager instead of the default global thread local one.
    config.add_settings({
        "tm.manager_hook": "warehouse.transactions.manager_hook",
    })

    # Include pyramid_tm so that it registers the transaction tween.
    config.include("pyramid_tm")
