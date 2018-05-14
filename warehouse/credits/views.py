from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config

from .contributors import Contributor

@view_config(
    route_name="credits",
    renderer="pages/credits.html"
)
def credits_page(request):

    # test data mbacchi FIXME
    # contributors = [{'contributor_login':'mbacchi',
    #                  'contributor_name':'Matt Bacchi',
    #                  'contributor_url': 'https://github.com/mbacchi'},
    #                 {'contributor_login':'someone',
    #                  'contributor_name':'Blank Name',
    #                  'contributor_url': 'https://github.com/someone'},
    #                 ]

    # get all items from Contributors table
    contributors = request.db.query(Contributor).order_by(Contributor.contributor_name)
    # print(contributors)

    return {'contributors': contributors}
