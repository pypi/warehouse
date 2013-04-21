import pytest

from django.core.urlresolvers import reverse


@pytest.mark.django_db(transaction=True)
def test_simple_signup(webtest):
    form = webtest.get(reverse("accounts.signup")).form
    form["username"] = "testuser"
    form["email"] = "testuser@example.com"
    form["password"] = "test password!"
    form["confirm_password"] = "test password!"
    response = form.submit()

    assert response.status_code == 303
