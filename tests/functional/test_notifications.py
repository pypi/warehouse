# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from warehouse.i18n import LOCALE_ATTR


class TestLocale:
    def test_unauthed_user(self, webtest):
        """
        Test that locale changes are reflected in the response
        """
        # The default locale is set to English
        resp = webtest.get("/", status=HTTPStatus.OK)
        assert LOCALE_ATTR not in resp.headers.getall("Set-Cookie")
        assert resp.html.find("html").attrs["lang"] == "en"

        # Change to a different locale
        resp = webtest.get(
            "/locale/?locale=es",
            params={"locale_id": "es"},
            status=HTTPStatus.SEE_OTHER,
        )
        # assert that the locale cookie is set in one of the cookies
        assert f"{LOCALE_ATTR}=es; Path=/" in resp.headers.getall("Set-Cookie")
        # Follow the redirect and check if the locale is set and flash notice appears
        next_page = resp.follow(status=HTTPStatus.OK)
        assert next_page.html.find("html").attrs["lang"] == "es"
        # Fetch the client-side includes and confirm the flash notice
        resp = webtest.get("/_includes/unauthed/flash-messages/", status=HTTPStatus.OK)
        success_message = resp.html.find("span", {"class": "notification-bar__message"})
        assert success_message.text != "Locale updated"  # Value in Spanish, may change

        # Switch back to English
        resp = webtest.get(
            "/locale/?locale=en",
            params={"locale_id": "en"},
            status=HTTPStatus.SEE_OTHER,
        )
        assert f"{LOCALE_ATTR}=en; Path=/" in resp.headers.getall("Set-Cookie")
        next_page = resp.follow(status=HTTPStatus.OK)
        assert next_page.html.find("html").attrs["lang"] == "en"
        # Fetch the client-side includes and confirm the flash notice
        resp = webtest.get("/_includes/unauthed/flash-messages/", status=HTTPStatus.OK)
        success_message = resp.html.find("span", {"class": "notification-bar__message"})
        assert success_message.text == "Locale updated"
