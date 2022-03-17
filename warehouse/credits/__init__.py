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

from warehouse.credits.tasks import get_contributors


def includeme(config):
    # Add a periodic task to get contributors every 24 hours
    if config.get_settings().get("github.token"):
        config.add_periodic_task(crontab(minute="2", hour="2"), get_contributors)
