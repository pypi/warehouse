# SPDX-License-Identifier: Apache-2.0

from warehouse.accounts.models import ProhibitedEmailDomain
from warehouse.accounts.utils import prohibit_email_domain


class TestProhibitEmailDomain:
    def test_empty_domain_is_refused(self, db_request):
        """
        A domain='' row would match every address whose host has no
        registrable domain, and the admin UI has no way to delete it, so
        an empty domain is refused outright rather than inserted.
        """
        assert prohibit_email_domain(db_request.db, "") is False
        assert db_request.db.query(ProhibitedEmailDomain).all() == []

    def test_non_empty_domain_is_added(self, db_request):
        assert prohibit_email_domain(db_request.db, "example.com") is True
        prohibited = db_request.db.query(ProhibitedEmailDomain).one()
        assert prohibited.domain == "example.com"
