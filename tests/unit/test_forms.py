# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from webob.multidict import MultiDict
from wtforms.validators import ValidationError

from warehouse.forms import (
    PasswordStrengthValidator,
    PreventHTMLTagsValidator,
    SetLocaleForm,
    URIValidator,
)


class TestURIValidator:
    @pytest.mark.parametrize(
        "uri",
        [
            "https://example.com/",
            "http://example.com/",
            "https://sub.example.com/path?query#thing",
        ],
    )
    def test_valid(self, uri):
        URIValidator()(pretend.stub(), pretend.stub(data=uri))

    @pytest.mark.parametrize(
        "uri", ["javascript:alert(0)", "UNKNOWN", "ftp://example.com/"]
    )
    def test_invalid(self, uri):
        validator = URIValidator()
        with pytest.raises(ValidationError):
            validator(pretend.stub(), pretend.stub(data=uri))

    def test_plain_schemes(self):
        validator = URIValidator(require_scheme=True, allowed_schemes=[])
        validator(pretend.stub(), pretend.stub(data="ftp://example.com/"))


class TestPasswordStrengthValidator:
    def test_invalid_fields(self):
        validator = PasswordStrengthValidator(user_input_fields=["foo"])
        with pytest.raises(ValidationError) as exc:
            validator({}, pretend.stub())
        assert str(exc.value) == "Invalid field name: 'foo'"

    @pytest.mark.parametrize("password", ["this is a great password!"])
    def test_good_passwords(self, password):
        validator = PasswordStrengthValidator()
        validator(pretend.stub(), pretend.stub(data=password))

    @pytest.mark.parametrize(
        ("password", "expected"),
        [
            (
                "qwerty",
                (
                    "This is a top-10 common password. Add another word or two. "
                    "Uncommon words are better."
                ),
            ),
            (
                "bombo!b",
                (
                    "Password is too easily guessed. Add another word or two. "
                    "Uncommon words are better."
                ),
            ),
            ("bombo!b asdadad", "Password is too easily guessed."),
        ],
    )
    def test_invalid_password(self, password, expected):
        validator = PasswordStrengthValidator(required_strength=5)
        with pytest.raises(ValidationError) as exc:
            validator(pretend.stub(), pretend.stub(data=password))
        assert str(exc.value) == expected


class TestPreventHTMLTagsValidator:
    @pytest.mark.parametrize(
        "inbound_data",
        [
            "A link https://example.com",
            "query string https://example.com?query=string",
            "anchor https://example.com#fragment",
            "qs and anchor https://example.com?query=string#fragment",
            "path, qs, anchor https://example.com/path?query=string#fragment",
            "A comment with a > character",
            "A comment with a < character",
            "A comment with a & character",
            "A comment with a ' character",
            'A comment with a " character',
        ],
    )
    def test_valid(self, inbound_data):
        validator = PreventHTMLTagsValidator()
        validator(pretend.stub(), pretend.stub(data=inbound_data))

    def test_invalid(self):
        validator = PreventHTMLTagsValidator()
        with pytest.raises(ValidationError) as exc:
            validator(
                pretend.stub(), pretend.stub(data="<img src='https://example.com'>")
            )

        assert str(exc.value) == "HTML tags are not allowed"

    def test_custom_message(self):
        validator = PreventHTMLTagsValidator(message="No HTML allowed")
        with pytest.raises(ValidationError) as exc:
            validator(
                pretend.stub(), pretend.stub(data="<img src='https://example.com'>")
            )

        assert str(exc.value) == "No HTML allowed"


class TestSetLocaleForm:
    def test_validate(self):
        form = SetLocaleForm(MultiDict({"locale_id": "es"}))
        assert form.validate(), str(form.errors)
