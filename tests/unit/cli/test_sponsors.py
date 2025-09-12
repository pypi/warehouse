# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse import db
from warehouse.cli import sponsors
from warehouse.sponsors.models import Sponsor


def raise_(ex):
    """
    Used by lambda functions to raise exception
    """
    raise ex


def test_populate_sponsors_from_sponsors_dict(db_request, monkeypatch, cli):
    engine = pretend.stub()
    config = pretend.stub(registry={"sqlalchemy.engine": engine})
    session_cls = pretend.call_recorder(lambda bind: db_request.db)
    monkeypatch.setattr(db, "Session", session_cls)

    assert 0 == db_request.db.query(Sponsor).count()
    cli.invoke(sponsors.populate_db, obj=config)
    assert len(sponsors.SPONSORS_DICTS) == db_request.db.query(Sponsor).count()
    assert session_cls.calls == [pretend.call(bind=engine)]

    # assert sponsors have the correct data
    for sponsor_dict in sponsors.SPONSORS_DICTS:
        db_sponsor = (
            db_request.db.query(Sponsor)
            .filter(Sponsor.name == sponsor_dict["name"])
            .one()
        )
        assert db_sponsor.is_active
        assert sponsor_dict["url"] == db_sponsor.link_url
        assert sponsor_dict.get("service") == db_sponsor.service
        assert sponsor_dict["footer"] == db_sponsor.footer
        assert sponsor_dict["psf_sponsor"] == db_sponsor.psf_sponsor
        assert sponsor_dict["infra_sponsor"] == db_sponsor.infra_sponsor
        assert sponsor_dict["one_time"] == db_sponsor.one_time
        assert sponsor_dict["sidebar"] == db_sponsor.sidebar
        assert (
            sponsors.BLACK_BASE_URL + sponsor_dict["image"] == db_sponsor.color_logo_url
        )
        # infra or footer sponsors must have white logo url
        if db_sponsor.footer or db_sponsor.infra_sponsor:
            assert (
                sponsors.WHITE_BASE_URL + sponsor_dict["image"]
                == db_sponsor.white_logo_url
            )
        else:
            assert db_sponsor.white_logo_url is None


def test_do_not_duplicate_existing_sponsors(db_request, monkeypatch, cli):
    engine = pretend.stub()
    config = pretend.stub(registry={"sqlalchemy.engine": engine})
    session_cls = pretend.call_recorder(lambda bind: db_request.db)
    monkeypatch.setattr(db, "Session", session_cls)

    # command line called several times
    cli.invoke(sponsors.populate_db, obj=config)
    cli.invoke(sponsors.populate_db, obj=config)
    cli.invoke(sponsors.populate_db, obj=config)

    # still with the same amount of sponsors in the DB
    assert len(sponsors.SPONSORS_DICTS) == db_request.db.query(Sponsor).count()


def test_capture_exception_if_error_and_rollback(db_request, monkeypatch, cli):
    engine = pretend.stub()
    config = pretend.stub(registry={"sqlalchemy.engine": engine})
    session = pretend.stub()
    session.add = pretend.call_recorder(lambda obj: raise_(Exception("SQL exception")))
    session.rollback = pretend.call_recorder(lambda: True)
    session.commit = pretend.call_recorder(lambda: True)
    session.query = db_request.db.query
    session_cls = pretend.call_recorder(lambda bind: session)
    monkeypatch.setattr(db, "Session", session_cls)

    cli.invoke(sponsors.populate_db, obj=config)

    # no new data at db and no exception being raised
    assert 0 == db_request.db.query(Sponsor).count()
    assert len(session.add.calls) == len(sponsors.SPONSORS_DICTS)
    assert len(session.rollback.calls) == len(sponsors.SPONSORS_DICTS)
    assert len(session.commit.calls) == 0
