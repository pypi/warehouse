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

import wtforms

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.forms import Form, URIValidator
from warehouse.sponsors.models import Sponsor


class SponsorForm(Form):
    name = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=100),
            wtforms.validators.DataRequired(),
        ],
    )
    service = wtforms.fields.StringField(
        validators=[wtforms.validators.Length(max=256), wtforms.validators.Optional()]
    )

    link_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            URIValidator(),
        ]
    )
    color_logo_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Optional(),
            URIValidator(),
        ]
    )
    white_logo_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Optional(),
            URIValidator(),
        ]
    )

    activity_markdown = wtforms.fields.TextAreaField(render_kw={"rows": 10, "cols": 60})

    is_active = wtforms.fields.BooleanField(default=False)
    footer = wtforms.fields.BooleanField()
    psf_sponsor = wtforms.fields.BooleanField()
    infra_sponsor = wtforms.fields.BooleanField()
    one_time = wtforms.fields.BooleanField()
    sidebar = wtforms.fields.BooleanField()


@view_config(
    route_name="admin.sponsor.list",
    renderer="admin/sponsors/list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def sponsor_list(request):
    sponsors = request.db.query(Sponsor).order_by(Sponsor.is_active.desc(), Sponsor.name).all()
    for sponsor in sponsors:
        visibility = [
            "PSF Sponsor" if sponsor.psf_sponsor else None,
            "Infra Sponsor" if sponsor.infra_sponsor else None,
            "One time" if sponsor.one_time else None,
            "Footer" if sponsor.footer else None,
            "Sidebar" if sponsor.sidebar else None,
        ]
        sponsor.visibility = " | ".join([v for v in visibility if v])
    return {"sponsors": sponsors}


@view_config(
    route_name="admin.sponsor.edit",
    renderer="admin/sponsors/edit.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.sponsor.edit",
    renderer="admin/sponsors/edit.html",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def edit_sponsor(request):
    id_ = request.matchdict["sponsor_id"]
    try:
        sponsor = request.db.query(Sponsor).filter(Sponsor.id == id_).one()
    except NoResultFound:
        raise HTTPNotFound

    form = SponsorForm(request.POST if request.method == "POST" else None, sponsor)

    if request.method == "POST" and form.validate():
        form.populate_obj(sponsor)
        return HTTPSeeOther(location=request.current_route_path())

    return {"sponsor": sponsor, "form": form}


@view_config(
    route_name="admin.sponsor.create",
    renderer="admin/sponsors/edit.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.sponsor.create",
    renderer="admin/sponsors/edit.html",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def create_sponsor(request):
    form = SponsorForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.validate():
        sponsor = Sponsor(**form.data)
        request.db.add(sponsor)
        request.session.flash(
            f"Added new sponsor '{sponsor.name}'",
            queue="success",
        )
        redirect_url = request.route_url("admin.sponsor.list")
        return HTTPSeeOther(location=redirect_url)

    return {"form": form}
