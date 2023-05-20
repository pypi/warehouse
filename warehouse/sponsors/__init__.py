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

from celery.schedules import crontab
from sqlalchemy import true

from warehouse.sponsors.models import Sponsor
from warehouse.sponsors.tasks import update_pypi_sponsors


def _sponsors(request):
    return request.db.query(Sponsor).filter(Sponsor.is_active == true()).all()


def includeme(config):
    # Add a request method which will allow to list sponsors
    config.add_request_method(_sponsors, name="sponsors", reify=True)

    # Add a periodic task to update sponsors table
    if config.registry.settings.get("pythondotorg.api_token"):
        config.add_periodic_task(crontab(minute=10), update_pypi_sponsors)
