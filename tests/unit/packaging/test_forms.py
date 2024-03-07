# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
