# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.oidc.view_mixins import PendingOIDCPublisherViewMixin


class TestPendingOIDCPublisherViewMixin:
    def test_default_response_unimplemented(self):
        with pytest.raises(NotImplementedError):
            PendingOIDCPublisherViewMixin().default_response  # noqa: B018

    @pytest.mark.parametrize(
        ("hook", "args"),
        [
            ("_pending_count_scope", ()),
            ("_too_many_pending_message", ()),
            ("_ratelimited_response", (None,)),
            ("_record_pending_publisher_added", ({},)),
            ("_pending_publisher_added_message", (None,)),
        ],
    )
    def test_hooks_unimplemented(self, hook, args):
        with pytest.raises(NotImplementedError):
            getattr(PendingOIDCPublisherViewMixin(), hook)(*args)
