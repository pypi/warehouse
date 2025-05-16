# SPDX-License-Identifier: Apache-2.0

import os
import secrets
import tempfile

import wtforms

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from slugify import slugify
from sqlalchemy.exc import NoResultFound

from warehouse.admin.interfaces import ISponsorLogoStorage
from warehouse.authnz import Permissions
from warehouse.forms import URIValidator
from warehouse.sponsors.models import Sponsor


class SponsorForm(wtforms.Form):
    name = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=100),
            wtforms.validators.InputRequired(),
        ],
    )
    service = wtforms.fields.StringField(
        validators=[wtforms.validators.Length(max=256), wtforms.validators.Optional()]
    )

    link_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            URIValidator(),
        ]
    )
    color_logo = wtforms.fields.FileField()
    color_logo_url = wtforms.fields.StringField(
        validators=[
            URIValidator(),
        ]
    )
    white_logo = wtforms.fields.FileField()
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

    def validate(self, *args, **kwargs):
        if not super().validate(*args, **kwargs):
            return False

        require_white_logo = self.footer.data or self.infra_sponsor.data
        if require_white_logo and not self.white_logo_url.data:
            self.white_logo.errors.append(
                "Must upload white logo if is a footer sponsor."
            )
            return False

        return True


@view_config(
    route_name="admin.sponsor.list",
    renderer="admin/sponsors/list.html",
    permission=Permissions.AdminSponsorsRead,
    request_method="GET",
    uses_session=True,
)
def sponsor_list(request):
    sponsors = (
        request.db.query(Sponsor).order_by(Sponsor.is_active.desc(), Sponsor.name).all()
    )
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


def _upload_image(image_name, request, form):
    sponsor_name = slugify(form.name.data)
    if request.POST.get(image_name) not in [None, b""]:
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(request.POST[image_name].file.read())
            fp.flush()
            content_type = request.POST[image_name].type
            storage = request.find_service(ISponsorLogoStorage)
            extension = os.path.splitext(request.POST[image_name].filename)[-1]
            fingerprint = secrets.token_urlsafe(6)
            filename = f"{sponsor_name}-{slugify(image_name)}-{fingerprint}{extension}"
            return storage.store(filename, fp.name, content_type)
    return ""


@view_config(
    route_name="admin.sponsor.edit",
    renderer="admin/sponsors/edit.html",
    permission=Permissions.AdminSponsorsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.sponsor.edit",
    renderer="admin/sponsors/edit.html",
    permission=Permissions.AdminSponsorsWrite,
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

    if request.method == "POST":
        if _color_logo_url := _upload_image("color_logo", request, form):
            form.color_logo_url.data = _color_logo_url
        if _white_logo_url := _upload_image("white_logo", request, form):
            form.white_logo_url.data = _white_logo_url
        if form.validate():
            form.populate_obj(sponsor)
            request.session.flash("Sponsor updated", queue="success")
            return HTTPSeeOther(location=request.current_route_path())

    return {"sponsor": sponsor, "form": form}


@view_config(
    route_name="admin.sponsor.create",
    renderer="admin/sponsors/edit.html",
    permission=Permissions.AdminSponsorsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.sponsor.create",
    renderer="admin/sponsors/edit.html",
    permission=Permissions.AdminSponsorsWrite,
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def create_sponsor(request):
    form = SponsorForm(request.POST if request.method == "POST" else None)

    if request.method == "POST":
        form.color_logo_url.data = _upload_image("color_logo", request, form)
        form.white_logo_url.data = _upload_image("white_logo", request, form)
        if form.validate():
            del form.color_logo
            del form.white_logo
            sponsor = Sponsor(**form.data)
            request.db.add(sponsor)
            request.session.flash(
                f"Added new sponsor '{sponsor.name}'",
                queue="success",
            )
            redirect_url = request.route_url("admin.sponsor.list")
            return HTTPSeeOther(location=redirect_url)

    return {"form": form}


@view_config(
    route_name="admin.sponsor.delete",
    require_methods=["POST"],
    permission=Permissions.AdminSponsorsWrite,
    uses_session=True,
    require_csrf=True,
)
def delete_sponsor(request):
    id_ = request.matchdict["sponsor_id"]
    try:
        sponsor = request.db.query(Sponsor).filter(Sponsor.id == id_).one()
    except NoResultFound:
        raise HTTPNotFound

    # Safeguard check on sponsor name
    if sponsor.name != request.params.get("sponsor"):
        request.session.flash("Wrong confirmation input", queue="error")
        return HTTPSeeOther(
            request.route_url("admin.sponsor.edit", sponsor_id=sponsor.id)
        )

    # Delete the sponsor
    request.db.delete(sponsor)
    request.session.flash(f"Deleted sponsor {sponsor.name}", queue="success")
    return HTTPSeeOther(request.route_url("admin.sponsor.list"))
