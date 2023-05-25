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
from sqlalchemy.exc import NoResultFound

from warehouse.banners.models import Banner
from warehouse.forms import Form, URIValidator


@view_config(
    route_name="admin.banner.list",
    renderer="admin/banners/list.html",
    permission="admin_dashboard_access",
    request_method="GET",
    uses_session=True,
)
def banner_list(request):
    banners = request.db.query(Banner).all()
    return {"banners": banners}


@view_config(
    route_name="admin.banner.edit",
    renderer="admin/banners/edit.html",
    permission="admin_dashboard_access",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.banner.edit",
    renderer="admin/banners/edit.html",
    permission="psf_staff",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def edit_banner(request):
    id_ = request.matchdict["banner_id"]
    try:
        banner = request.db.query(Banner).filter(Banner.id == id_).one()
    except NoResultFound:
        raise HTTPNotFound

    form = BannerForm(request.POST if request.method == "POST" else None, banner)

    if request.method == "POST" and form.validate():
        form.populate_obj(banner)
        request.session.flash("Banner updated", queue="success")
        return HTTPSeeOther(location=request.current_route_path())

    return {"banner": banner, "form": form}


@view_config(
    route_name="admin.banner.create",
    renderer="admin/banners/edit.html",
    permission="admin_dashboard_access",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.banner.create",
    renderer="admin/banners/edit.html",
    permission="psf_staff",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def create_banner(request):
    form = BannerForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.validate():
        banner = Banner(**form.data)
        request.db.add(banner)
        request.session.flash(
            f"Added new banner '{banner.name}'",
            queue="success",
        )
        redirect_url = request.route_url("admin.banner.list")
        return HTTPSeeOther(location=redirect_url)

    return {"form": form}


@view_config(
    route_name="admin.banner.delete",
    require_methods=["POST"],
    permission="psf_staff",
    uses_session=True,
    require_csrf=True,
)
def delete_banner(request):
    id_ = request.matchdict["banner_id"]
    try:
        banner = request.db.query(Banner).filter(Banner.id == id_).one()
    except NoResultFound:
        raise HTTPNotFound

    # Safeguard check on banner name
    if banner.name != request.params.get("banner"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(request.route_url("admin.banner.edit", banner_id=banner.id))

    # Delete the banner
    request.db.delete(banner)
    request.session.flash(f"Deleted banner {banner.name}", queue="success")
    return HTTPSeeOther(request.route_url("admin.banner.list"))


@view_config(
    route_name="admin.banner.preview",
    require_methods=["GET"],
    permission="moderator",
    uses_session=True,
    require_csrf=True,
    has_translations=True,
    renderer="admin/banners/preview.html",
)
def preview_banner(request):
    id_ = request.matchdict["banner_id"]
    try:
        banner = request.db.query(Banner).filter(Banner.id == id_).one()
        return {"banner": banner}
    except NoResultFound:
        raise HTTPNotFound


class BannerForm(Form):
    name = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=100),
            wtforms.validators.InputRequired(),
        ],
    )
    text = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=280),
            wtforms.validators.InputRequired(),
        ],
    )
    link_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            URIValidator(),
        ]
    )
    link_label = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Optional(),
        ],
        default=Banner.DEFAULT_BTN_LABEL,
    )
    fa_icon = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=40),
            wtforms.validators.Optional(),
        ],
        default=Banner.DEFAULT_FA_ICON,
    )
    active = wtforms.fields.BooleanField(
        validators=[wtforms.validators.Optional()], default=False
    )
    end = wtforms.fields.DateField(validators=[wtforms.validators.InputRequired()])
