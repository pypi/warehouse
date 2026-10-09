# SPDX-License-Identifier: Apache-2.0

import logging

import pytest

from pyramid.response import Response
from pyramid.tweens import EXCVIEW

from warehouse.rate_limiting import notfound


def _tween(status):
    return notfound.notfound_ratelimit_tween_factory(
        lambda request: Response(status=status), None
    )


class TestNotFoundRateLimitTween:
    def test_ignores_non_404(
        self, pyramid_request, notfound_ratelimit_service, metrics
    ):
        response = _tween(200)(pyramid_request)

        assert response.status_code == 200
        notfound_ratelimit_service.hit.assert_not_called()
        metrics.increment.assert_not_called()

    def test_under_limit(
        self, pyramid_request, notfound_ratelimit_service, metrics, caplog
    ):
        response = _tween(404)(pyramid_request)

        assert response.status_code == 404
        notfound_ratelimit_service.hit.assert_called_once_with("1.2.3.4")
        metrics.increment.assert_called_once_with(
            "warehouse.ratelimit.hit", tags=["limiter:notfound.ip"]
        )
        # Cached 404s are shared across clients, so no RateLimit headers.
        assert not hasattr(pyramid_request, "_rate_limit_snapshots")
        assert caplog.records == []

    @pytest.mark.parametrize(("sample", "logged"), [(0, True), (1, False)])
    def test_over_limit(
        self,
        pyramid_request,
        notfound_ratelimit_service,
        metrics,
        caplog,
        mocker,
        sample,
        logged,
    ):
        """Every over-limit 404 is counted; only a sample is logged."""
        notfound_ratelimit_service.hit.return_value = False
        randbelow = mocker.patch.object(notfound, "randbelow", return_value=sample)
        pyramid_request.path = "/pypi/missing/json"

        with caplog.at_level(logging.WARNING):
            response = _tween(404)(pyramid_request)

        assert response.status_code == 404
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.ratelimit.hit", tags=["limiter:notfound.ip"]),
            mocker.call("warehouse.ratelimit.exceeded", tags=["limiter:notfound.ip"]),
        ]
        randbelow.assert_called_once_with(notfound.EXCEEDED_LOG_SAMPLE)
        if logged:
            (record,) = caplog.records
            assert record.getMessage() == "404 rate limit exceeded"
            assert record.remote_addr == pyramid_request.remote_addr_hashed
            assert record.path == "/pypi/missing/json"
        else:
            assert caplog.records == []

    @pytest.mark.parametrize("remote_addr", [None, "not-an-ip"])
    def test_skips_without_client_ip(
        self, pyramid_request, notfound_ratelimit_service, metrics, remote_addr
    ):
        pyramid_request.remote_addr = remote_addr

        response = _tween(404)(pyramid_request)

        assert response.status_code == 404
        notfound_ratelimit_service.hit.assert_not_called()
        metrics.increment.assert_not_called()

    def test_canonicalizes_ipv6(self, pyramid_request, notfound_ratelimit_service):
        pyramid_request.remote_addr = "2001:DB8:0:0::1"

        _tween(404)(pyramid_request)

        notfound_ratelimit_service.hit.assert_called_once_with("2001:db8::1")


def test_includeme(mocker):
    config = mocker.Mock(
        registry=mocker.Mock(
            settings={"warehouse.notfound.ip_ratelimit_string": "50 per 5 minutes"}
        )
    )

    notfound.includeme(config)

    config.register_rate_limiter.assert_called_once_with(
        "50 per 5 minutes", "notfound.ip"
    )
    config.add_tween.assert_called_once_with(
        "warehouse.rate_limiting.notfound.notfound_ratelimit_tween_factory",
        over=EXCVIEW,
    )
