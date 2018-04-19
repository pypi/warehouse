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

import pretend
import pytest

from warehouse.admin.views import classifiers as views
from warehouse.classifiers.models import Classifier

from ....common.db.classifiers import ClassifierFactory


class TestGetClassifiers:

    def test_get_classifiers(self, db_request):
        classifier_a = ClassifierFactory(classifier='I am first')
        classifier_b = ClassifierFactory(classifier='I am last')

        assert views.get_classifiers(db_request) == {
            'classifiers': [classifier_a, classifier_b],
        }


class TestAddClassifier:

    @pytest.mark.parametrize(
        'parent_levels, expected_levels',
        [
            ((2, 0, 0, 0), (2, None, 0, 0)),
            ((2, 3, 0, 0), (2, 3, None, 0)),
            ((2, 3, 4, 0), (2, 3, 4, None)),

            # This won't actually happen but it's needed for coverage
            ((2, 3, 4, 5), (2, 3, 4, 5)),
        ]
    )
    def test_add_child_classifier(
            self, db_request, parent_levels, expected_levels):
        l2, l3, l4, l5 = parent_levels
        parent = ClassifierFactory(
            l2=l2, l3=l3, l4=l4, l5=l5, classifier='Parent'
        )

        db_request.params = {
            'parent_id': parent.id,
            'child': 'Foobar',
        }
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.route_path = lambda *a: '/the/path'

        views.AddClassifier(db_request).add_child_classifier()

        new = (
            db_request.db.query(Classifier)
            .filter(Classifier.classifier == 'Parent :: Foobar')
            .one()
        )

        new_l2, new_l3, new_l4, new_l5 = expected_levels
        assert new.l2 == new_l2 if new_l2 is not None else new.id
        assert new.l3 == new_l3 if new_l3 is not None else new.id
        assert new.l4 == new_l4 if new_l4 is not None else new.id
        assert new.l5 == new_l5 if new_l5 is not None else new.id

    def test_add_parent_classifier(self, db_request):
        db_request.params = {'parent': 'Foo :: Bar'}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.route_path = lambda *a: '/the/path'

        views.AddClassifier(db_request).add_parent_classifier()

        new = (
            db_request.db.query(Classifier)
            .filter(Classifier.classifier == 'Foo :: Bar')
            .one()
        )

        assert new.l2 == new.id
        assert new.l3 == 0
        assert new.l4 == 0
        assert new.l5 == 0


class TestDeprecateClassifier:

    def test_deprecate_classifier(self, db_request):
        classifier = ClassifierFactory(deprecated=False)

        db_request.params = {'classifier_id': classifier.id}
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.route_path = lambda *a: '/the/path'

        views.deprecate_classifier(db_request)
        db_request.db.flush()

        assert classifier.deprecated
