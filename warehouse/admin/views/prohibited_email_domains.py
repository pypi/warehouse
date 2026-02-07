# SPDX-License-Identifier: Apache-2.0

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import exists, select
from tldextract import TLDExtract

from warehouse.accounts.models import ProhibitedEmailDomain
from warehouse.authnz import Permissions
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.prohibited_email_domains.list",
    renderer="warehouse.admin:templates/admin/prohibited_email_domains/list.html",
    permission=Permissions.AdminProhibitedEmailDomainsRead,
    request_method="GET",
    uses_session=True,
)
def prohibited_email_domains(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    prohibited_email_domains_query = request.db.query(ProhibitedEmailDomain).order_by(
        ProhibitedEmailDomain.created.desc()
    )

    if q:
        prohibited_email_domains_query = prohibited_email_domains_query.filter(
            ProhibitedEmailDomain.domain.ilike(q)
        )

    prohibited_email_domains = SQLAlchemyORMPage(
        prohibited_email_domains_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"prohibited_email_domains": prohibited_email_domains, "query": q}


@view_config(
    route_name="admin.prohibited_email_domains.add",
    permission=Permissions.AdminProhibitedEmailDomainsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def add_prohibited_email_domain(request):
    email_domain = request.POST.get("email_domain")
    if not email_domain:
        request.session.flash("Email domain is required.", queue="error")
        raise HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))
    # validate that the domain is valid
    extractor = TLDExtract(suffix_list_urls=())  # Updated during image build
    registered_domain = extractor(email_domain).top_domain_under_public_suffix
    if not registered_domain:
        request.session.flash(f"Invalid domain name '{email_domain}'", queue="error")
        raise HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))
    # make sure we don't have a duplicate entry
    if request.db.scalar(
        select(exists().where(ProhibitedEmailDomain.domain == registered_domain))
    ):
        request.session.flash(
            f"Email domain '{registered_domain}' already exists.", queue="error"
        )
        raise HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))

    # Add the domain to the database
    is_mx_record = bool(request.POST.get("is_mx_record"))
    comment = request.POST.get("comment")

    prohibited_email_domain = ProhibitedEmailDomain(
        domain=registered_domain,
        is_mx_record=is_mx_record,
        prohibited_by=request.user,
        comment=comment,
    )

    request.db.add(prohibited_email_domain)
    request.session.flash("Prohibited email domain added.", queue="success")

    return HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))


@view_config(
    route_name="admin.prohibited_email_domains.remove",
    permission=Permissions.AdminProhibitedEmailDomainsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def remove_prohibited_email_domain(request):
    domain_name = request.POST.get("domain_name")
    if not domain_name:
        request.session.flash("Domain name is required.", queue="error")
        raise HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))

    domain_record = (
        request.db.query(ProhibitedEmailDomain)
        .filter(ProhibitedEmailDomain.domain == domain_name)
        .first()
    )

    if not domain_record:
        request.session.flash("Domain not found.", queue="error")
        raise HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))

    request.db.delete(domain_record)
    request.session.flash(
        f"Prohibited email domain '{domain_record.domain}' removed.", queue="success"
    )

    return HTTPSeeOther(request.route_path("admin.prohibited_email_domains.list"))
