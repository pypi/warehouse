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


class ValidationException(Exception):
    ...


@view_config(
    route_name="admin.classifiers",
    renderer="admin/classifiers/index.html",
    permission="admin",
    uses_session=True,
)
def get_classifiers(request):
    classifiers = request.db.query(Classifier).order_by(Classifier.classifier).all()

    return {"classifiers": classifiers}


@view_defaults(
    route_name="admin.classifiers.add",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
class AddClassifier:
    def __init__(self, request):
        self.request = request

    @view_config(request_param=["parent"])
    def add_parent_classifier(self):
        classifier = Classifier(
            classifier=self.request.params.get("parent"), l3=0, l4=0, l5=0
        )

        self.request.db.add(classifier)
        self.request.db.flush()  # To get the ID

        classifier.l2 = classifier.id

        self.request.session.flash(
            f"Added classifier {classifier.classifier!r}", queue="success"
        )

        return HTTPSeeOther(self.request.route_path("admin.classifiers"))

    @view_config(request_param=["parent_id", "child"])
    def add_child_classifier(self):
        parent = self.request.db.query(Classifier).get(
            self.request.params.get("parent_id")
        )

        classifier = Classifier(
            l2=parent.l2,
            l3=parent.l3,
            l4=parent.l4,
            l5=parent.l5,
            classifier=(parent.classifier + " :: " + self.request.params.get("child")),
        )
        self.request.db.add(classifier)
        self.request.db.flush()  # To get the ID

        for level in ["l3", "l4", "l5"]:
            if getattr(classifier, level) == 0:
                setattr(classifier, level, classifier.id)
                break

        self.request.session.flash(
            f"Added classifier {classifier.classifier!r}", queue="success"
        )

        return HTTPSeeOther(self.request.route_path("admin.classifiers"))


@view_config(
    route_name="admin.classifiers.deprecate",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
    request_param=["classifier_id"],
)
def deprecate_classifier(request):
    deprecated_classifier_id = int(request.params.get("classifier_id"))
    alternative_classifier_ids = {
        int(alternative_classifier_id)
        for alternative_classifier_id in request.params.getall("deprecated_by")
        if alternative_classifier_id
    }

    deprecated_classifier = request.db.query(Classifier).get(deprecated_classifier_id)

    try:
        if deprecated_classifier_id in alternative_classifier_ids:
            raise ValidationException(
                f"You can not deprecate the classifier in favor of itself"
            )

        alternative_classifiers = []
        for alternative_classifier_id in alternative_classifier_ids:
            alternative_classifier = request.db.query(Classifier).get(
                alternative_classifier_id
            )
            if alternative_classifier.deprecated:
                # It is not a 100% protection from circular dependencies, because if
                # exactly at the same moment
                # one admin will deprecate classifier A in favor of classifier B,
                # and another admin will deprecate classifier B in favor of classifier A
                # this will create a circular dependency.
                raise ValidationException(
                    f"You can not deprecate the classifier "
                    f"{deprecated_classifier.classifier!r} "
                    f"in favor of already deprecated classifier "
                    f"{alternative_classifier.classifier!r}"
                )
            else:
                alternative_classifiers.append(alternative_classifier)
    except ValidationException as e:
        request.session.flash(e.args[0], queue="error")
        return HTTPSeeOther(request.route_path("admin.classifiers"))

    deprecated_classifier.deprecated = True
    for alternative_classifier in alternative_classifiers:
        deprecated_classifier.alternatives.append(alternative_classifier)

    message = f"Deprecated classifier {deprecated_classifier.classifier!r}"
    if alternative_classifiers:
        message += f" in favor of " + ", ".join(
            f"{alternative_classifier.classifier!r}"
            for alternative_classifier in alternative_classifiers
        )

    request.session.flash(message, queue="success")

    return HTTPSeeOther(request.route_path("admin.classifiers"))
