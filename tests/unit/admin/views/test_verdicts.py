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

    def test_check_name_filter(self, db_request):
        check1 = MalwareCheckFactory.create()
        check2 = MalwareCheckFactory.create()
        check3 = MalwareCheckFactory.create()
        verdicts1 = [MalwareVerdictFactory.create(check=check1) for _ in range(10)]
        verdicts2 = [MalwareVerdictFactory.create(check=check2) for _ in range(10)]

        response = {
            "verdicts": verdicts1,
            "check_names": set([check1.name, check2.name, check3.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        db_request.GET["check_name"] = check1.name
        assert views.get_verdicts(db_request) == response

        db_request.GET["check_name"] = check2.name
        response["verdicts"] = verdicts2
        assert views.get_verdicts(db_request) == response

        db_request.GET["check_name"] = check3.name
        response["verdicts"] = []
        assert views.get_verdicts(db_request) == response

        db_request.GET["check_name"] = ""
        response["verdicts"] = verdicts1 + verdicts2
        assert views.get_verdicts(db_request) == response

        db_request.GET["check_name"] = "DoesNotExist"
        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request) == response

    def test_classification_filter(self, db_request):
        check1 = MalwareCheckFactory.create()
        verdicts1 = [
            MalwareVerdictFactory.create(
                check=check1, classification=VerdictClassification.Threat
            )
            for _ in range(10)
        ]
        verdicts2 = [
            MalwareVerdictFactory.create(
                check=check1, classification=VerdictClassification.Indeterminate
            )
            for _ in range(10)
        ]
        verdicts3 = [
            MalwareVerdictFactory.create(
                check=check1, classification=VerdictClassification.Benign
            )
            for _ in range(5)
        ]

        db_request.GET["classification"] = "threat"
        response = {
            "verdicts": verdicts1,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }
        assert views.get_verdicts(db_request) == response

        db_request.GET["classification"] = "indeterminate"
        response["verdicts"] = verdicts2
        assert views.get_verdicts(db_request) == response

        db_request.GET["classification"] = ""
        response["verdicts"] = verdicts1 + verdicts2 + verdicts3
        assert views.get_verdicts(db_request) == response

        db_request.GET["classification"] = "NotAClassification"
        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request)

    def test_confidence_filter(self, db_request):
        check1 = MalwareCheckFactory.create()
        verdicts1 = [
            MalwareVerdictFactory.create(check=check1, confidence=VerdictConfidence.Low)
            for _ in range(10)
        ]
        verdicts2 = [
            MalwareVerdictFactory.create(
                check=check1, confidence=VerdictConfidence.Medium
            )
            for _ in range(10)
        ]
        verdicts3 = [
            MalwareVerdictFactory.create(
                check=check1, confidence=VerdictConfidence.High
            )
            for _ in range(5)
        ]

        db_request.GET["confidence"] = "low"
        response = {
            "verdicts": verdicts1,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }
        assert views.get_verdicts(db_request) == response

        db_request.GET["confidence"] = "high"
        response["verdicts"] = verdicts3
        assert views.get_verdicts(db_request) == response

        db_request.GET["confidence"] = ""
        response["verdicts"] = verdicts1 + verdicts2 + verdicts3
        assert views.get_verdicts(db_request) == response

        db_request.GET["confidence"] = "NotAConfidence"
        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request) == response

    def test_manually_reviewed_filter(self, db_request):
        check1 = MalwareCheckFactory.create()
        verdicts1 = [
            MalwareVerdictFactory.create(check=check1, manually_reviewed=False)
            for _ in range(10)
        ]
        verdicts2 = [
            MalwareVerdictFactory.create(check=check1, manually_reviewed=True)
            for _ in range(10)
        ]

        response = {
            "verdicts": verdicts1,
            "check_names": set([check1.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        db_request.GET["manually_reviewed"] = "0"
        assert views.get_verdicts(db_request) == response

        db_request.GET["manually_reviewed"] = "1"
        response["verdicts"] = verdicts2
        assert views.get_verdicts(db_request) == response

        db_request.GET["manually_reviewed"] = "nope"

        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request)

    def test_with_invalid_page(self, db_request):
        db_request.GET["page"] = "not an integer"

        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(db_request)


class TestGetVerdict:
    def test_found(self, db_request):
        verdicts = [MalwareVerdictFactory.create() for _ in range(10)]
        index = randint(0, 9)
        lookup_id = verdicts[index].id
        db_request.matchdict["verdict_id"] = lookup_id

        assert views.get_verdict(db_request) == {"verdict": verdicts[index]}

    def test_not_found(self, db_request):
        db_request.matchdict["verdict_id"] = uuid.uuid4()

        with pytest.raises(HTTPNotFound):
            views.get_verdict(db_request)
