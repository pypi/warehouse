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
        assert success_message.text == "Se actualizó la configuración de idioma"
