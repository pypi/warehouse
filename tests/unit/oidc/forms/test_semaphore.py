# SPDX-License-Identifier: Apache-2.0

import pretend

from webob.multidict import MultiDict

from warehouse.oidc import forms


class TestPendingSemaphorePublisherForm:
    def test_validate(self, pyramid_request):
        form = forms.PendingSemaphorePublisherForm(
            MultiDict(
                {
                    "organization": "example-org",
                    "project": "example-project",
                    "project_name": "example-pypi-project",
                }
            ),
            route_url=pyramid_request.route_url,
            check_project_name=lambda name: True,
            user=pretend.stub(),
        )

        assert form.validate()

    def test_validate_organization_required(self, pyramid_request):
        form = forms.PendingSemaphorePublisherForm(
            MultiDict(
                {
                    "project": "example-project",
                    "project_name": "example-pypi-project",
                }
            ),
            route_url=pyramid_request.route_url,
            check_project_name=lambda name: True,
            user=pretend.stub(),
        )

        assert not form.validate()
        assert "organization" in form.errors

    def test_validate_project_required(self, pyramid_request):
        form = forms.PendingSemaphorePublisherForm(
            MultiDict(
                {
                    "organization": "example-org",
                    "project_name": "example-pypi-project",
                }
            ),
            route_url=pyramid_request.route_url,
            check_project_name=lambda name: True,
            user=pretend.stub(),
        )

        assert not form.validate()
        assert "project" in form.errors

    def test_validate_organization_format(self, pyramid_request):
        form = forms.PendingSemaphorePublisherForm(
            MultiDict(
                {
                    "organization": "invalid org!",
                    "project": "example-project",
                    "project_name": "example-pypi-project",
                }
            ),
            route_url=pyramid_request.route_url,
            check_project_name=lambda name: True,
            user=pretend.stub(),
        )

        assert not form.validate()
        assert "organization" in form.errors

    def test_provider_property(self, pyramid_request):
        form = forms.PendingSemaphorePublisherForm(
            data={
                "organization": "example-org",
                "project": "example-project",
                "project_name": "example-pypi-project",
            },
            route_url=pyramid_request.route_url,
            check_project_name=lambda name: True,
            user=pretend.stub(),
        )

        assert form.provider == "semaphore"


class TestSemaphorePublisherForm:
    def test_validate(self):
        form = forms.SemaphorePublisherForm(
            MultiDict(
                {
                    "organization": "example-org",
                    "project": "example-project",
                }
            )
        )

        assert form.validate()

    def test_validate_organization_required(self):
        form = forms.SemaphorePublisherForm(
            MultiDict(
                {
                    "project": "example-project",
                }
            )
        )

        assert not form.validate()
        assert "organization" in form.errors

    def test_validate_project_required(self):
        form = forms.SemaphorePublisherForm(
            MultiDict(
                {
                    "organization": "example-org",
                }
            )
        )

        assert not form.validate()
        assert "project" in form.errors
