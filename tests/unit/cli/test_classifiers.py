# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import db
from warehouse.classifiers.models import Classifier
from warehouse.cli import classifiers


def test_classifiers_update(db_request, monkeypatch, cli):
    engine = pretend.stub()
    config = pretend.stub(registry={"sqlalchemy.engine": engine})
    session_cls = pretend.call_recorder(lambda bind: db_request.db)
    monkeypatch.setattr(db, "Session", session_cls)

    cs = [
        c.classifier
        for c in db_request.db.query(Classifier).order_by(Classifier.ordering).all()
    ]

    monkeypatch.setattr(classifiers, "sorted_classifiers", ["C :: D", "A :: B"] + cs)

    db_request.db.add(Classifier(classifier="A :: B", ordering=0))
    assert db_request.db.query(Classifier).filter_by(classifier="C :: D").count() == 0
    cli.invoke(classifiers.sync, obj=config)

    c = db_request.db.query(Classifier).filter_by(classifier="C :: D").one()

    assert c.classifier == "C :: D"
    assert c.ordering == 0

    c = db_request.db.query(Classifier).filter_by(classifier="A :: B").one()

    assert c.classifier == "A :: B"
    assert c.ordering == 1


def test_classifiers_no_update(db_request, monkeypatch, cli):
    engine = pretend.stub()
    config = pretend.stub(registry={"sqlalchemy.engine": engine})
    session_cls = pretend.call_recorder(lambda bind: db_request.db)
    monkeypatch.setattr(db, "Session", session_cls)

    original = db_request.db.query(Classifier).order_by(Classifier.ordering).all()

    monkeypatch.setattr(
        classifiers, "sorted_classifiers", [c.classifier for c in original]
    )

    cli.invoke(classifiers.sync, obj=config)

    after = db_request.db.query(Classifier).order_by(Classifier.ordering).all()

    assert original == after
