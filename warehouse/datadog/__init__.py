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

import os

from datadog import DogStatsd


def includeme(config):
    config.include(".pyramid_datadog")
    config.configure_metrics(
        DogStatsd(
            host=os.environ.get('DATADOG_HOST', '127.0.0.1'),
            port=int(os.environ.get('DATADOG_PORT', 8125)),
            namespace=os.environ.get('DATADOG_NAMESPACE'),
            use_ms=True,
            use_default_route=bool(
                os.environ.get('DATADOG_USE_DEFAULT_ROUTE')
            ),
        )
    )
