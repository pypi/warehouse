# SPDX-License-Identifier: Apache-2.0

import types

from warehouse import db
from warehouse.cli import sponsors
from warehouse.sponsors.models import Sponsor


def test_populate_sponsors_from_sponsors_dict(db_request, mocker, cli):
    engine = mocker.sentinel.engine
    config = types.SimpleNamespace(registry={"sqlalchemy.engine": engine})
    session_cls = mocker.patch.object(db, "Session", return_value=db_request.db)

    assert db_request.db.query(Sponsor).count() == 0
    cli.invoke(sponsors.populate_db, obj=config)
    assert len(sponsors.SPONSORS_DICTS) == db_request.db.query(Sponsor).count()
    session_cls.assert_called_once_with(bind=engine)

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


def test_do_not_duplicate_existing_sponsors(db_request, mocker, cli):
    engine = mocker.sentinel.engine
    config = types.SimpleNamespace(registry={"sqlalchemy.engine": engine})
    mocker.patch.object(db, "Session", return_value=db_request.db)

    # command line called several times
    cli.invoke(sponsors.populate_db, obj=config)
    cli.invoke(sponsors.populate_db, obj=config)
    cli.invoke(sponsors.populate_db, obj=config)

    # still with the same amount of sponsors in the DB
    assert len(sponsors.SPONSORS_DICTS) == db_request.db.query(Sponsor).count()


def test_capture_exception_if_error_and_rollback(db_request, mocker, cli):
    engine = mocker.sentinel.engine
    config = types.SimpleNamespace(registry={"sqlalchemy.engine": engine})
    add = mocker.patch.object(
        db_request.db, "add", side_effect=Exception("SQL exception")
    )
    rollback = mocker.spy(db_request.db, "rollback")
    commit = mocker.spy(db_request.db, "commit")
    mocker.patch.object(db, "Session", return_value=db_request.db)

    cli.invoke(sponsors.populate_db, obj=config)

    # no new data at db and no exception being raised
    assert db_request.db.query(Sponsor).count() == 0
    assert add.call_count == len(sponsors.SPONSORS_DICTS)
    assert rollback.call_count == len(sponsors.SPONSORS_DICTS)
    assert commit.call_count == 0
