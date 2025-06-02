# SPDX-License-Identifier: Apache-2.0

from webob.multidict import MultiDict

from warehouse.packaging.forms import SubmitMalwareObservationForm


class TestSubmitObservationForm:
    inspector_link = "https://inspector.pypi.io/project/requests/"

    def test_validate(self, pyramid_request):
        pyramid_request.POST = MultiDict(
            {
                "inspector_link": self.inspector_link,
                "summary": "This is a comment",
            }
        )

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert form.validate({"comment": "This is a comment"})

    def test_missing_inspector_link(self, pyramid_request):
        pyramid_request.POST = MultiDict({"summary": "This is a comment"})

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "inspector_link" in form.errors

    def test_malformed_inspector_link(self, pyramid_request):
        pyramid_request.POST = MultiDict(
            {
                "inspector_link": "https://inspector.pypi.org/project/requests/",
                "summary": "This is a comment",
            }
        )

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "inspector_link" in form.errors

    def test_missing_summary(self, pyramid_request):
        pyramid_request.POST = MultiDict({"inspector_link": self.inspector_link})

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "summary" in form.errors

    def test_summary_too_short(self, pyramid_request):
        pyramid_request.POST = MultiDict(
            {
                "inspector_link": self.inspector_link,
                "summary": "short",
            }
        )

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "summary" in form.errors

    def test_summary_too_long(self, pyramid_request):
        pyramid_request.POST = MultiDict(
            {
                "inspector_link": self.inspector_link,
                "summary": "x" * 2001,
            }
        )

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "summary" in form.errors

    def test_summary_contains_html_tags(self, pyramid_request):
        pyramid_request.POST = MultiDict(
            {
                "inspector_link": self.inspector_link,
                "summary": '<img src="https://example.com/image.png">',
            }
        )

        form = SubmitMalwareObservationForm(pyramid_request.POST)

        assert not form.validate()
        assert "summary" in form.errors
