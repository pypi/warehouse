import secrets
import string

from urllib.parse import urlparse

import pytest

from pytest_bdd import given, scenario, then, when


@scenario("login.feature", "Login")
def test_login():
    pass


@pytest.fixture
def user_info():
    return {
        "username": "john",
        "name": "John Doe",
        "password": "".join(secrets.choice(string.ascii_letters) for _ in range(20)),
    }


@given("I am a user")
def user(user_service, user_info):
    user = user_service.create_user(**user_info)
    user_service.db.commit()
    return user


@when("I go to the login page")
def navigate_to_login(server_url, browser):
    browser.open(f"{server_url}/account/login/")
    assert browser.get_current_page().find("h1").text == "Log in to PyPI"


@when("I enter my credentials")
def correct_credentials_input(browser, user_info):
    browser.select_form('form[action="/account/login/"]')
    browser["username"] = user_info["username"]
    browser["password"] = user_info["password"]


@when("I submit the form")
def click_form(browser):
    browser.submit_selected()


@then("I should be on my projects page")
def check_my_projects_page(browser):
    assert urlparse(browser.get_url()).path == "/manage/projects/"
    assert "Your projects" in browser.get_current_page().find("h1").text


@scenario("login.feature", "Failed login")
def test_failed_login():
    pass


@when("I enter wrong credentials")
def incorrect_credentials_input(browser, user_info):
    browser.select_form('form[action="/account/login/"]')
    browser["username"] = user_info["username"]
    browser["password"] = user_info["password"] + "foo"


@then("I should be on the login page")
def check_login_page(browser, server_url):
    assert urlparse(browser.get_url()).path == "/account/login/"


@then("an invalid password error should be displayed")
def check_invalid_password_error(browser):
    error = browser.get_current_page().select_one("#password-errors li")
    assert error.text == "The password is invalid. Try again."


@scenario("login.feature", "Logout")
def test_logout():
    pass


@given("I am logged in")
def logged_in(browser, user_info, server_url):
    browser.open(f"{server_url}/account/login/")
    browser.select_form('form[action="/account/login/"]')
    browser["username"] = user_info["username"]
    browser["password"] = user_info["password"]
    browser.submit_selected()


@when("I open the account menu")
def open_menu(browser, server_url):
    browser.open(f"{server_url}/_includes/current-user-indicator/")


@when("I click on the logout button")
def click_logout(browser):
    browser.select_form('form[action="/account/logout/"]')
    browser.submit_selected()


@then("I should be on the home page")
def check_home_page(browser, server_url):
    assert urlparse(browser.get_url()).path == "/"


@when("I go to my projects page")
def navigate_to_my_projects(server_url, browser):
    browser.open(f"{server_url}/manage/projects/")


@then("there should be a login link")
def check_login_link(browser, server_url):
    login_link = browser.get_current_page().select_one('a[href="/account/login/"]')
    assert login_link.text == "Log in"
