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

import jinja2

from markupsafe import Markup as M  # noqa

from warehouse.filters import tojson


_L20N_TEMPLATE = jinja2.Template(
    'data-l10n-id="{{ tid }}"'
    '{% if data %} data-l10n-args="{{ data }}"{% endif %}',
    autoescape=True,
)


def l20n(tid, **kwargs):
    data = tojson(kwargs) if kwargs else None
    return M(_L20N_TEMPLATE.render(tid=tid, data=data))
