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

    contrib_count = contributors.count()

    # separate the list into two lists to be used in the two column layout
    separated = [contributors[0:int(contrib_count/2)],
                 contributors[int(contrib_count/2):contrib_count]]

    return {'contributors': separated}
