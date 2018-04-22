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

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config, view_defaults

from warehouse.packaging.models import Classifier


@view_config(
    route_name="admin.classifiers",
    renderer="admin/classifiers/index.html",
    permission="admin",
    uses_session=True,
)
def get_classifiers(request):
    classifiers = (
        request.db.query(Classifier)
        .order_by(Classifier.classifier)
        .all()
    )

    return {
        'classifiers': classifiers,
    }


@view_defaults(
    route_name='admin.classifiers.add',
    permission='admin',
    request_method='POST',
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
class AddClassifier:

    def __init__(self, request):
        self.request = request

    @view_config(request_param=['parent'])
    def add_parent_classifier(self):
        classifier = Classifier(
            classifier=self.request.params.get('parent'), l3=0, l4=0, l5=0,
        )

        self.request.db.add(classifier)
        self.request.db.flush()  # To get the ID

        classifier.l2 = classifier.id

        self.request.session.flash(
            f'Successfully added classifier {classifier.classifier!r}',
            queue='success',
        )

        return HTTPSeeOther(self.request.route_path('admin.classifiers'))

    @view_config(request_param=['parent_id', 'child'])
    def add_child_classifier(self):
        parent = (
            self.request.db
            .query(Classifier)
            .get(self.request.params.get('parent_id'))
        )

        classifier = Classifier(
            l2=parent.l2,
            l3=parent.l3,
            l4=parent.l4,
            l5=parent.l5,
            classifier=(
                parent.classifier + ' :: ' + self.request.params.get('child')
            ),
        )
        self.request.db.add(classifier)
        self.request.db.flush()  # To get the ID

        for level in ['l3', 'l4', 'l5']:
            if getattr(classifier, level) == 0:
                setattr(classifier, level, classifier.id)
                break

        self.request.session.flash(
            f'Successfully added classifier {classifier.classifier!r}',
            queue='success',
        )

        return HTTPSeeOther(self.request.route_path('admin.classifiers'))


@view_config(
    route_name='admin.classifiers.deprecate',
    permission='admin',
    request_method='POST',
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def deprecate_classifier(request):
    classifier = (
        request.db
        .query(Classifier)
        .get(request.params.get('classifier_id'))
    )

    classifier.deprecated = True

    request.session.flash(
        f'Successfully deprecated classifier {classifier.classifier!r}',
        queue='success',
    )

    return HTTPSeeOther(request.route_path('admin.classifiers'))
