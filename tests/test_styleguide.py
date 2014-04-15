from warehouse.styleguide import FlaskSessionCheck

import pep8

# These are sadly globals -- there is no unregister_check.
pep8.register_check(FlaskSessionCheck)


def test_flask_absolute_session_import_fails():
    TEST_IMPORT = "import flask.session\n\n"
    checker = pep8.Checker(lines=TEST_IMPORT, quiet=True)
    checker.check_all()
    assert checker.report.get_count(FlaskSessionCheck.CODE) == 1


def test_flask_relative_session_import_fails():
    TEST_IMPORT_FROM = [
        "from foo import bar\n",
        "from flask import session\n",
        "import foo\n",
        "\n"
    ]
    checker = pep8.Checker(lines=TEST_IMPORT_FROM, quiet=True)
    checker.check_all()
    assert checker.report.get_count(FlaskSessionCheck.CODE) == 1


def test_ordinary_imports_fine():
    TEST_SAFE_IMPORT = "from warehouse.foo import bar\n\n"
    checker = pep8.Checker(lines=TEST_SAFE_IMPORT, quiet=True)
    checker.check_all()
    assert checker.report.get_count(FlaskSessionCheck.CODE) == 0
