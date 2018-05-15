from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config

from .contributors import Contributor

@view_config(
    route_name="credits",
    renderer="pages/credits.html"
)
def credits_page(request):

    # get all items from Contributors table
    contributors = request.db.query(Contributor).order_by(Contributor.contributor_name)

    return {'contributors': contributors}
