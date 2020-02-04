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

import uuid

from random import randint

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.admin.views import verdicts as views
from warehouse.malware.models import VerdictClassification, VerdictConfidence

from ....common.db.malware import MalwareCheckFactory, MalwareVerdictFactory


class TestListVerdicts:
    def test_none(self, db_request):
        assert views.get_verdicts(db_request) == {
            "verdicts": [],
            "check_names": set(),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

    def test_some(self, db_request):
        check = MalwareCheckFactory.create()
        verdicts = [MalwareVerdictFactory.create(check=check) for _ in range(10)]

        assert views.get_verdicts(db_request) == {
            "verdicts": verdicts,
            "check_names": set([check.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

    def test_some_with_multipage(self, db_request):
        check1 = MalwareCheckFactory.create()
        check2 = MalwareCheckFactory.create()
        verdicts = [MalwareVerdictFactory.create(check=check2) for _ in range(60)]

        db_request.GET["page"] = "2"

        assert views.get_verdicts(db_request) == {
            "verdicts": verdicts[25:50],
            "check_names": set([check1.name, check2.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

    @pytest.mark.parametrize(
        "check_name", ["check0", "check1", ""],
    )
    def test_check_name_filter(self, db_request, check_name):
        result_verdicts, all_verdicts = [], []
        for i in range(3):
            check = MalwareCheckFactory.create(name="check%d" % i)
            verdicts = [MalwareVerdictFactory.create(check=check) for _ in range(5)]
            all_verdicts.extend(verdicts)
            if check.name == check_name:
                result_verdicts = verdicts

        # Emptry string
        if not result_verdicts:
            result_verdicts = all_verdicts

        response = {
            "verdicts": result_verdicts,
            "check_names": set(["check0", "check1", "check2"]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        db_request.GET["check_name"] = check_name
        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "classification", ["benign", "indeterminate", "threat", ""],
    )
    def test_classification_filter(self, db_request, classification):
        check1 = MalwareCheckFactory.create()
        result_verdicts, all_verdicts = [], []
        for c in VerdictClassification:
            verdicts = [
                MalwareVerdictFactory.create(check=check1, classification=c)
                for _ in range(5)
            ]
            all_verdicts.extend(verdicts)
            if c.value == classification:
                result_verdicts = verdicts

        # Emptry string
        if not result_verdicts:
            result_verdicts = all_verdicts

        db_request.GET["classification"] = classification
        response = {
            "verdicts": result_verdicts,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }
        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "confidence", ["low", "medium", "high", ""],
    )
    def test_confidence_filter(self, db_request, confidence):
        check1 = MalwareCheckFactory.create()
        result_verdicts, all_verdicts = [], []
        for c in VerdictConfidence:
            verdicts = [
                MalwareVerdictFactory.create(check=check1, confidence=c)
                for _ in range(5)
            ]
            all_verdicts.extend(verdicts)
            if c.value == confidence:
                result_verdicts = verdicts

        # Emptry string
        if not result_verdicts:
            result_verdicts = all_verdicts

        response = {
            "verdicts": result_verdicts,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        db_request.GET["confidence"] = confidence
        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "manually_reviewed", [1, 0],
    )
    def test_manually_reviewed_filter(self, db_request, manually_reviewed):
        check1 = MalwareCheckFactory.create()
        result_verdicts = [
            MalwareVerdictFactory.create(
                check=check1, manually_reviewed=bool(manually_reviewed)
            )
            for _ in range(5)
        ]

        # Create other verdicts to ensure filter works properly
        for _ in range(10):
            MalwareVerdictFactory.create(
                check=check1, manually_reviewed=not bool(manually_reviewed)
            )

        db_request.GET["manually_reviewed"] = str(manually_reviewed)

        response = {
            "verdicts": result_verdicts,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "invalid_param",
        [
            ("page", "invalid"),
            ("check_name", "NotACheck"),
            ("confidence", "NotAConfidence"),
            ("classification", "NotAClassification"),
            ("manually_reviewed", "False"),
        ],
    )
    def test_errors(self, db_request, invalid_param):
        db_request.GET[invalid_param[0]] = invalid_param[1]
        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request)


class TestGetVerdict:
    def test_found(self, db_request):
        verdicts = [MalwareVerdictFactory.create() for _ in range(10)]
        index = randint(0, 9)
        lookup_id = verdicts[index].id
        db_request.matchdict["verdict_id"] = lookup_id

        assert views.get_verdict(db_request) == {
            "verdict": verdicts[index],
            "classifications": ["Benign", "Indeterminate", "Threat"],
        }

    def test_not_found(self, db_request):
        db_request.matchdict["verdict_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.get_verdict(db_request)


class TestReviewVerdict:
    @pytest.mark.parametrize(
        "manually_reviewed, administrator_verdict",
        [
            (False, None),  # unreviewed verdict
            (True, VerdictClassification.Threat),  # previously reviewed
        ],
    )
    def test_set_classification(
        self, db_request, manually_reviewed, administrator_verdict
    ):
        verdict = MalwareVerdictFactory.create(
            manually_reviewed=manually_reviewed,
            administrator_verdict=administrator_verdict,
        )

        db_request.matchdict["verdict_id"] = verdict.id
        db_request.POST = {"classification": "Benign"}
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/admin/verdicts/%s/review" % verdict.id
        )

        views.review_verdict(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Verdict %s marked as reviewed." % verdict.id, queue="success")
        ]

        assert verdict.manually_reviewed
        assert verdict.administrator_verdict == VerdictClassification.Benign

    @pytest.mark.parametrize("post_params", [{}, {"classification": "Nope"}])
    def test_errors(self, db_request, post_params):
        verdict = MalwareVerdictFactory.create()
        db_request.matchdict["verdict_id"] = verdict.id
        db_request.POST = post_params

        with pytest.raises(HTTPBadRequest):
            views.review_verdict(db_request)
