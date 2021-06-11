import datetime

from pyramid.view import view_config

from warehouse.banners.models import Banner


@view_config(
    route_name="includes.db-banners",
    renderer="includes/banner-messages.html",
    uses_session=True,
    has_translations=True,
)
def list_banner_messages(request):
    today = str(datetime.date.today())
    return {
        "banners": request.db.query(Banner)
        .filter((Banner.begin <= today) & (Banner.end >= today))
        .all()
    }
