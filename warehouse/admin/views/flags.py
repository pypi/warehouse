# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config

from warehouse.admin.flags import AdminFlag


@view_config(
    route_name='admin.flags',
    renderer='admin/flags/index.html',
    permission='admin',
    uses_session=True,
)
def get_flags(request):
    return {
        'flags': request.db.query(AdminFlag).order_by(AdminFlag.id).all(),
    }


@view_config(
    route_name='admin.flags.edit',
    permission='admin',
    request_method='POST',
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def edit_flag(request):
    flag = request.db.query(AdminFlag).get(request.POST['id'])
    flag.description = request.POST['description']
    flag.enabled = bool(request.POST.get('enabled'))

    request.session.flash(
        f'Successfully edited flag {flag.id!r}',
        queue='success',
    )

    return HTTPSeeOther(request.route_path('admin.flags'))
