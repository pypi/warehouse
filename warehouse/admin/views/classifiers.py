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
from pyramid.view import view_config

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
        .filter(Classifier.l5 == 0)  # Can be a parent
        .order_by(Classifier.classifier)
        .all()
    )

    return {
        'classifiers': classifiers,
    }


@view_config(
    route_name="admin.classifiers.add",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def add_classifier(request):
    parent = request.db.query(Classifier).get(request.params.get('parent_id'))

    classifier = Classifier(
        l2=parent.l2,
        l3=parent.l3,
        l4=parent.l4,
        l5=parent.l5,
        classifier=parent.classifier + " :: " + request.params.get('child'),
    )
    request.db.add(classifier)
    request.db.flush()  # To get the ID

    for level in ['l3', 'l4', 'l5']:
        if getattr(classifier, level) == 0:
            setattr(classifier, level, classifier.id)
            break

    request.session.flash(
        f"Successfully added classifier {classifier.classifier!r}",
        queue="success",
    )

    return HTTPSeeOther(request.route_path("admin.classifiers"))
