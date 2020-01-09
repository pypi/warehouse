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
from warehouse.malware.models import MalwareCheckType

from ....common.db.malware import MalwareCheckFactory, MalwareVerdictFactory
from ....common.db.packaging import ProjectFactory


class TestListVerdicts:
    def test_none(self, db_request):
        assert views.get_verdicts(db_request) == {"verdicts": []}

    def test_some(self, db_request):
        project = ProjectFactory.create()
        check = MalwareCheckFactory.create(
            check_type=MalwareCheckType.event_hook, hooked_object="Project"
        )
        verdicts = [
            MalwareVerdictFactory.create(
                check_id=check.id, project=project, release_file=None
            )
            for _ in range(10)
        ]

        assert views.get_verdicts(db_request) == {"verdicts": verdicts}

    def test_some_with_multipage(self, db_request):
        project = ProjectFactory.create()
        check = MalwareCheckFactory.create(
            check_type=MalwareCheckType.event_hook, hooked_object="Project"
        )
        verdicts = [
            MalwareVerdictFactory.create(
                check_id=check.id, project=project, release_file=None
            )
            for _ in range(60)
        ]

        db_request.GET["page"] = "2"

        assert views.get_verdicts(db_request) == {"verdicts": verdicts[25:50]}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.get_verdicts(request)


class TestGetVerdict:
    def test_found(self, db_request):
        project = ProjectFactory.create()
        check = MalwareCheckFactory.create(
            check_type=MalwareCheckType.event_hook, hooked_object="Project"
        )
        verdicts = [
            MalwareVerdictFactory.create(
                check_id=check.id, project=project, release_file=None
            )
            for _ in range(10)
        ]
        index = randint(1, 10)
        lookup_id = verdicts[index].id.hex
        db_request.matchdict["verdict_id"] = lookup_id

        assert views.get_verdict(db_request) == {"verdict": verdicts[index]}

    def test_not_found(self, db_request):
        db_request.matchdict["verdict_id"] = uuid.uuid4().hex

        with pytest.raises(HTTPNotFound):
            views.get_verdict(db_request)
