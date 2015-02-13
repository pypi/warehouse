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

import pretend
import pytest

from warehouse.forms import Form, DBForm, StopValidation


def _raiser(exc):
    raise exc


class TestForm:

    def test_empty_form_no_errors(self):
        form = Form()
        assert form.errors == {}

    def test_errors_is_cached(self):
        form = Form()
        assert form.errors == {}
        form._form_errors.append("An Error")
        assert form.errors == {}
        form._errors = None
        assert form.errors == {"__all__": ["An Error"]}

    def test_form_level_validation_no_validators(self):
        class TestForm(Form):
            pass

        form = TestForm()

        assert form.validate()
        assert form.errors == {}

    def test_form_level_validation_full_validate(self):
        class TestForm(Form):
            @pretend.call_recorder
            def full_validate(self):
                pass

        form = TestForm()

        assert form.validate()
        assert form.errors == {}
        assert form.full_validate.calls == [pretend.call(form)]

    def test_form_level_validation_full_validate_fails(self):
        class TestForm(Form):
            @pretend.call_recorder
            def full_validate(self):
                raise ValueError("A Value Error")

        form = TestForm()

        assert not form.validate()
        assert form.errors == {"__all__": ["A Value Error"]}
        assert form.full_validate.calls == [pretend.call(form)]

    @pytest.mark.parametrize(
        "validator_funcs",
        [
            [],
            [lambda f: None]
        ],
    )
    def test_form_level_validation_meta_works(self, validator_funcs):
        validator_funcs = [pretend.call_recorder(v) for v in validator_funcs]

        class TestForm(Form):
            class Meta:
                validators = validator_funcs

        form = TestForm()

        assert form.validate()
        assert form.errors == {}
        for v in validator_funcs:
            assert v.calls == [pretend.call(form)]

    @pytest.mark.parametrize(
        ("validator_funcs", "errors", "stop_after"),
        [
            (
                [
                    lambda f: _raiser(ValueError("An Error")),
                    lambda f: None,
                    lambda f: _raiser(ValueError("Another Error")),
                    lambda f: _raiser(StopValidation("Stop!")),
                    lambda f: _raiser(ValueError("This Won't Show.")),
                ],
                ["An Error", "Another Error", "Stop!"],
                3,
            ),
            (
                [
                    lambda f: _raiser(ValueError("An Error")),
                    lambda f: None,
                    lambda f: _raiser(ValueError("Another Error")),
                    lambda f: _raiser(StopValidation),
                    lambda f: _raiser(ValueError("This Won't Show.")),
                ],
                ["An Error", "Another Error"],
                3,
            ),
        ],
    )
    def test_form_level_validation_meta_fails(self, validator_funcs, errors,
                                              stop_after):
        validator_funcs = [pretend.call_recorder(v) for v in validator_funcs]

        class TestForm(Form):
            class Meta:
                validators = validator_funcs

        form = TestForm()

        assert not form.validate()
        assert form.errors == {"__all__": errors}
        for i, v in enumerate(validator_funcs):
            assert v.calls == [pretend.call(form)]
            if i >= stop_after:
                break


class TestDBForm:

    def test_form_requires_db(self):
        with pytest.raises(TypeError):
            DBForm()

    def test_form_accepts_db(self):
        db = pretend.stub()
        form = DBForm(db=db)
        assert form.db is db
