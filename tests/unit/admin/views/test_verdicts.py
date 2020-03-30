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

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound

from warehouse.admin.views import verdicts as views
from warehouse.malware.models import (
    MalwareCheck,
    MalwareVerdict,
    VerdictClassification,
    VerdictConfidence,
)
from warehouse.utils.paginate import paginate_url_factory

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
        for _ in range(10):
            MalwareVerdictFactory.create(check=check)

        query = db_request.db.query(MalwareVerdict).order_by(
            MalwareVerdict.run_date.desc()
        )

        verdicts = SQLAlchemyORMPage(
            query,
            page=1,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        assert views.get_verdicts(db_request) == {
            "verdicts": verdicts,
            "check_names": set([check.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

    def test_some_with_multipage(self, db_request):
        check1 = MalwareCheckFactory.create()
        check2 = MalwareCheckFactory.create()
        for _ in range(60):
            MalwareVerdictFactory.create(check=check2)

        db_request.GET["page"] = "2"

        query = db_request.db.query(MalwareVerdict).order_by(
            MalwareVerdict.run_date.desc()
        )
        verdicts = SQLAlchemyORMPage(
            query,
            page=2,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        assert views.get_verdicts(db_request) == {
            "verdicts": verdicts,
            "check_names": set([check1.name, check2.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

    @pytest.mark.parametrize(
        "check_name", ["check0", "check1", ""],
    )
    def test_check_name_filter(self, db_request, check_name):
        for i in range(3):
            check = MalwareCheckFactory.create(name="check%d" % i)
            for _ in range(5):
                MalwareVerdictFactory.create(check=check)

        query = db_request.db.query(MalwareVerdict)
        if check_name:
            query = query.join(MalwareCheck).filter(MalwareCheck.name == check_name)
        query = query.order_by(MalwareVerdict.run_date.desc())

        verdicts = SQLAlchemyORMPage(
            query,
            page=1,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        response = {
            "verdicts": verdicts,
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
        check = MalwareCheckFactory.create()
        for c in VerdictClassification:
            for _ in range(5):
                MalwareVerdictFactory.create(check=check, classification=c)

        db_request.GET["classification"] = classification

        query = db_request.db.query(MalwareVerdict)
        if classification:
            query = query.filter(MalwareVerdict.classification == classification)
        query = query.order_by(MalwareVerdict.run_date.desc())

        verdicts = SQLAlchemyORMPage(
            query,
            page=1,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        response = {
            "verdicts": verdicts,
            "check_names": set([check.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }
        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "confidence", ["low", "medium", "high", ""],
    )
    def test_confidence_filter(self, db_request, confidence):
        check = MalwareCheckFactory.create()
        for c in VerdictConfidence:
            for _ in range(5):
                MalwareVerdictFactory.create(check=check, confidence=c)

        db_request.GET["confidence"] = confidence

        query = db_request.db.query(MalwareVerdict)
        if confidence:
            query = query.filter(MalwareVerdict.confidence == confidence)
        query = query.order_by(MalwareVerdict.run_date.desc())

        verdicts = SQLAlchemyORMPage(
            query,
            page=1,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        response = {
            "verdicts": verdicts,
            "check_names": set([check.name]),
            "classifications": set(["threat", "indeterminate", "benign"]),
            "confidences": set(["low", "medium", "high"]),
        }

        assert views.get_verdicts(db_request) == response

    @pytest.mark.parametrize(
        "manually_reviewed", [1, 0],
    )
    def test_manually_reviewed_filter(self, db_request, manually_reviewed):
        check = MalwareCheckFactory.create()
        for _ in range(5):
            MalwareVerdictFactory.create(
                check=check, manually_reviewed=bool(manually_reviewed)
            )

        # Create other verdicts to ensure filter works properly
        for _ in range(10):
            MalwareVerdictFactory.create(
                check=check, manually_reviewed=not bool(manually_reviewed)
            )

        db_request.GET["manually_reviewed"] = str(manually_reviewed)

        query = (
            db_request.db.query(MalwareVerdict)
            .filter(MalwareVerdict.manually_reviewed == bool(manually_reviewed))
            .order_by(MalwareVerdict.run_date.desc())
        )

        verdicts = SQLAlchemyORMPage(
            query,
            page=1,
            items_per_page=25,
            url_maker=paginate_url_factory(db_request),
        )

        response = {
            "verdicts": verdicts,
            "check_names": set([check.name]),
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
        "manually_reviewed, reviewer_verdict",
        [
            (False, None),  # unreviewed verdict
            (True, VerdictClassification.Threat),  # previously reviewed
        ],
    )
    def test_set_classification(self, db_request, manually_reviewed, reviewer_verdict):
        verdict = MalwareVerdictFactory.create(
            manually_reviewed=manually_reviewed, reviewer_verdict=reviewer_verdict,
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
        assert verdict.reviewer_verdict == VerdictClassification.Benign

    @pytest.mark.parametrize("post_params", [{}, {"classification": "Nope"}])
    def test_errors(self, db_request, post_params):
        verdict = MalwareVerdictFactory.create()
        db_request.matchdict["verdict_id"] = verdict.id
        db_request.POST = post_params

        with pytest.raises(HTTPBadRequest):
            views.review_verdict(db_request)
