# SPDX-License-Identifier: Apache-2.0

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import literal

from warehouse.accounts.models import ProhibitedUserName, User
from warehouse.admin.views.users import _nuke_user
from warehouse.authnz import Permissions
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.prohibited_user_names.list",
    renderer="admin/prohibited_user_names/list.html",
    permission=Permissions.AdminProhibitedUsernameRead,
    request_method="GET",
    uses_session=True,
)
def prohibited_usernames(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    prohibited_user_names_query = request.db.query(ProhibitedUserName).order_by(
        ProhibitedUserName.created.desc()
    )

    if q:
        prohibited_user_names_query = prohibited_user_names_query.filter(
            ProhibitedUserName.name.ilike(q)
        )

    prohibited_user_names = SQLAlchemyORMPage(
        prohibited_user_names_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"prohibited_user_names": prohibited_user_names, "query": q}


@view_config(
    route_name="admin.prohibited_user_names.bulk_add",
    renderer="admin/prohibited_user_names/bulk.html",
    permission=Permissions.AdminUsersWrite,
    uses_session=True,
    require_methods=False,
)
def bulk_add_prohibited_user_names(request):
    if request.method == "POST":
        user_names = request.POST.get("users", "").split()

        for user_name in user_names:
            # Check to make sure the prohibition doesn't already exist.
            if (
                request.db.query(literal(True))
                .filter(
                    request.db.query(ProhibitedUserName)
                    .filter(ProhibitedUserName.name == user_name.lower())
                    .exists()
                )
                .scalar()
            ):
                continue

            # Go through and delete the usernames

            user = request.db.query(User).filter(User.username == user_name).first()
            if user is not None:
                _nuke_user(user, request)
            else:
                request.db.add(
                    ProhibitedUserName(
                        name=user_name.lower(),
                        comment="nuked",
                        prohibited_by=request.user,
                    )
                )

        request.session.flash(f"Prohibited {len(user_names)!r} users", queue="success")

        return HTTPSeeOther(request.route_path("admin.prohibited_user_names.bulk_add"))
    return {}
