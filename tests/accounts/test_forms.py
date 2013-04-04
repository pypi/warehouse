from warehouse.accounts.forms import UserChangeForm


def test_user_change_form_initalizes():
    UserChangeForm()


def test_user_change_form_clean_password():
    form = UserChangeForm({"password": "fail"}, initial={"password": "epic"})
    assert form.clean_password() == "epic"
