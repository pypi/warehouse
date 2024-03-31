from tests.common.db.accounts import UserFactory
from sqlalchemy import text

def test_user_profile(db_session, webtest):
    user = UserFactory.create()
    assert user.username
    print(f"got user {user.username}", flush=True)
    result = db_session.execute(text("select * from users"))
    actual = ["; ".join([f"{s}" for s in row]) for row in result]
    print(actual, flush=True)
    # vist user's page
    resp = webtest.get(f"/user/{user.username}/")
    assert resp.status_code == 200
