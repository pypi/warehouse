# SPDX-License-Identifier: Apache-2.0

import types

from warehouse import db
from warehouse.classifiers.models import Classifier
from warehouse.cli import classifiers


def test_classifiers_update(db_request, mocker, cli):
    engine = mocker.sentinel.engine
    config = types.SimpleNamespace(registry={"sqlalchemy.engine": engine})
    mocker.patch.object(db, "Session", return_value=db_request.db)

    cs = [
        c.classifier
        for c in db_request.db.query(Classifier).order_by(Classifier.ordering).all()
    ]

    mocker.patch.object(classifiers, "sorted_classifiers", ["C :: D", "A :: B", *cs])

    db_request.db.add(Classifier(classifier="A :: B", ordering=0))
    assert db_request.db.query(Classifier).filter_by(classifier="C :: D").count() == 0
    cli.invoke(classifiers.sync, obj=config)

    c = db_request.db.query(Classifier).filter_by(classifier="C :: D").one()

    assert c.classifier == "C :: D"
    assert c.ordering == 0

    c = db_request.db.query(Classifier).filter_by(classifier="A :: B").one()

    assert c.classifier == "A :: B"
    assert c.ordering == 1


def test_classifiers_no_update(db_request, mocker, cli):
    engine = mocker.sentinel.engine
    config = types.SimpleNamespace(registry={"sqlalchemy.engine": engine})
    mocker.patch.object(db, "Session", return_value=db_request.db)

    original = db_request.db.query(Classifier).order_by(Classifier.ordering).all()

    mocker.patch.object(
        classifiers, "sorted_classifiers", [c.classifier for c in original]
    )

    cli.invoke(classifiers.sync, obj=config)

    after = db_request.db.query(Classifier).order_by(Classifier.ordering).all()

    assert original == after
