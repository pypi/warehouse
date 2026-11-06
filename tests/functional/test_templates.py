# SPDX-License-Identifier: Apache-2.0

import re

from pathlib import Path
from types import SimpleNamespace

import pytest

from jinja2 import Environment, FileSystemLoader

import warehouse
import warehouse.admin.components  # registers the components

from warehouse.attestations.models import (
    ProvenanceComparison,
    ProvenanceCounts,
    ProvenanceStatus,
    PublisherSource,
    PublisherWorkflow,
)

FILTERS = {
    "format_date": "warehouse.i18n.filters:format_date",
    "format_datetime": "warehouse.i18n.filters:format_datetime",
    "format_rfc822_datetime": "warehouse.i18n.filters:format_rfc822_datetime",
    "format_number": "warehouse.i18n.filters:format_number",
    "format_classifiers": "warehouse.filters:format_classifiers",
    "classifier_id": "warehouse.filters:classifier_id",
    "format_tags": "warehouse.filters:format_tags",
    "json": "warehouse.filters:tojson",
    "camoify": "warehouse.filters:camoify",
    "shorten_number": "warehouse.filters:shorten_number",
    "urlparse": "warehouse.filters:urlparse",
    "contains_valid_uris": "warehouse.filters:contains_valid_uris",
    "format_package_type": "warehouse.filters:format_package_type",
    "parse_version": "warehouse.filters:parse_version",
    "localize_datetime": "warehouse.filters:localize_datetime",
    "ctime": "warehouse.filters:ctime",
    "canonicalize_name": "packaging.utils:canonicalize_name",
    "is_recent": "warehouse.filters:is_recent",
}

# A compiled regex that matches a subject block, possibly with newlines inside
SUBJECT_BLOCK_EXPRESSION = re.compile(
    r"\{% block subject %}.*\{% endblock %}", re.DOTALL
)


def _make_env(dir_name: Path, extensions: tuple[str, ...] = ()) -> Environment:
    env = Environment(
        autoescape=True,
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
            *extensions,
        ],
        cache_size=0,
    )
    env.filters.update(FILTERS)
    return env


@pytest.mark.parametrize(
    "template",
    [
        f.relative_to(Path(warehouse.__path__[0]) / "templates")
        for f in Path(warehouse.__path__[0]).glob("templates/**/*.html")
    ],
)
def test_templates_for_empty_titles(template: Path):
    """
    Test if all HTML templates have defined the title block. See
    https://github.com/pypi/warehouse/issues/784
    """
    env = _make_env(Path(warehouse.__path__[0]) / "templates")

    if any(
        parent.name in ["includes", "api", "legacy", "email"]
        for parent in template.parents
    ):
        # Skips specific directories, which are not expected to have titles.
        return

    template_obj = env.get_template(str(template))
    assert "title" in template_obj.blocks or "title_base" in template_obj.blocks


@pytest.mark.parametrize(
    "template",
    [
        f.relative_to(Path(warehouse.__path__[0]) / "templates")
        for f in Path(warehouse.__path__[0]).glob("templates/**/*.html")
    ],
)
def test_render_templates(template):
    """
    Test if all HTML templates are rendered without Jinja exceptions.
    see https://github.com/pypi/warehouse/issues/6634
    """
    env = _make_env(Path(warehouse.__path__[0]) / "templates")

    assert env.get_template(str(template))


@pytest.mark.parametrize(
    "template",
    [
        f.relative_to(Path(warehouse.__path__[0]) / "admin" / "templates")
        for f in Path(warehouse.__path__[0]).glob("admin/templates/**/*.html")
    ],
)
def test_render_admin_templates(template):
    """
    Test if all admin HTML templates are rendered without Jinja exceptions.

    The admin templates live outside `warehouse/templates`, so neither
    `test_render_templates` nor `bin/lint`'s djlint invocation reaches them.
    """
    env = _make_env(
        Path(warehouse.__path__[0]) / "admin" / "templates",
        extensions=("pyramid_components.jinja2.ComponentExtension",),
    )

    assert env.get_template(str(template))


@pytest.mark.parametrize(
    "email_name", ["organization-deactivated", "organization-subscription-required"]
)
def test_organization_email_subject_is_bounded(email_name: str) -> None:
    env = _make_env(Path(warehouse.__path__[0]) / "templates")
    organizations = [{"name": f"organization-{i:04}-{'x' * 32}"} for i in range(100)]
    request = SimpleNamespace(registry=SimpleNamespace(settings={"site.name": "PyPI"}))

    subject = env.get_template(f"email/{email_name}/subject.txt").render(
        organizations=organizations, request=request
    )

    assert len(subject) <= 100
    assert "100" in subject


@pytest.mark.parametrize(
    "email_name",
    [
        "new-organization-approved",
        "new-organization-declined",
        "new-organization-moreinformationneeded",
    ],
)
def test_organization_review_email_keeps_message_paragraphs(email_name: str) -> None:
    env = _make_env(Path(warehouse.__path__[0]) / "templates")
    env.install_null_translations(newstyle=True)
    request = SimpleNamespace(
        registry=SimpleNamespace(
            settings={"site.name": "PyPI", "warehouse.domain": "pypi.org"}
        ),
        route_url=lambda *args, **kwargs: "https://pypi.org/manage/",
    )

    html = env.get_template(f"email/{email_name}/body.html").render(
        request=request,
        organization_name="example",
        organization_application_id="00000000-0000-0000-0000-000000000000",
        organization_type="Community",
        # Browsers submit textareas with CRLF line endings.
        message=(
            "Hello <b>you</b>!\r\n\r\nFirst ask,\r\nsame paragraph.\r\n\r\n\r\nLast."
        ),
    )

    assert "<p>Hello &lt;b&gt;you&lt;/b&gt;!</p>" in html
    assert "<p>First ask,\nsame paragraph.</p>" in html
    assert "<p>Last.</p>" in html


@pytest.mark.parametrize(
    "template",
    list(Path(warehouse.__path__[0]).glob("templates/email/**/subject.txt")),
)
def test_email_subjects_for_multiple_lines(template: Path):
    """
    Test if all email subject templates don't contain new lines. See
    https://github.com/pypi/warehouse/issues/13216
    """

    with template.open("r") as f:
        match = SUBJECT_BLOCK_EXPRESSION.search(f.read())
        # There should be a subject block inside a subject template file
        assert match is not None
        # There should NOT be a newline inside the subject block
        assert "\n" not in match.group(0)


def test_all_templates_exist(app_config):
    """
    It's possible that the template passed into a @view_config() decorator does
    not actually exist, which would typically not be discovered until runtime
    when we attempt to render that template.

    So we'll go through all of our registered templates (which will be registered
    by @view_config()) and make sure that they do, in fact, exist.
    """
    # Gets a list of all of our templates as "asset spec" paths, which looks
    # like import.package.name:some/relative/file/path.ext, as well as the name
    # of the renderer that they're using.
    templates = [
        (i["introspectable"]["name"], i["introspectable"]["type"])
        for i in app_config.registry.introspector.get_category("templates")
    ]

    # Go through each template, and use the jinja2.Environment to determine if
    # the file that it points to actually exists.
    for template, renderer in templates:
        env = app_config.get_jinja2_environment(name=renderer)
        assert env is not None, f"{renderer} is not a jinja2 template type"
        env.get_template(template)  # this will raise TemplateNotFound


def test_provenance_warning_templates_render_urls():
    env = _make_env(Path(warehouse.__path__[0]) / "templates")
    env.install_null_translations()
    request = SimpleNamespace(
        route_path=lambda _route, name, version: f"/project/{name}/{version}/",
        user_docs_url=lambda path, anchor: f"https://docs.pypi.org{path}#{anchor}",
    )
    old_source = PublisherSource("GitHub", "foo/old", url="https://github.com/foo/old")
    new_source = PublisherSource("GitLab", "foo/new", url="https://gitlab.com/foo/new")
    google_source = PublisherSource(
        "Google", "ci@example.iam.gserviceaccount.com", is_account=True
    )
    old_workflow = PublisherWorkflow(
        "GitHub",
        "foo/old",
        "release.yml",
        url="https://github.com/foo/old/blob/aaa/.github/workflows/release.yml",
    )
    new_workflow = PublisherWorkflow(
        "GitLab",
        "foo/new",
        ".gitlab-ci.yml",
        url="https://gitlab.com/foo/new/blob/bbb//.gitlab-ci.yml",
    )

    counts = ProvenanceCounts(
        total_files=3,
        files_with_provenance=3,
        files_with_sources=3,
        files_with_workflows=2,
        source_counts={new_source: 1, google_source: 2},
        workflow_counts={old_workflow: 1, new_workflow: 1},
    )
    comparison = ProvenanceComparison(
        version="1.0.0",
        counts=ProvenanceCounts(
            total_files=1,
            files_with_provenance=1,
            files_with_sources=1,
            files_with_workflows=1,
            source_counts={old_source: 1},
            workflow_counts={old_workflow: 1},
        ),
    )
    release = SimpleNamespace(
        version="2.0.0",
        project=SimpleNamespace(name="sampleproject"),
        provenance_status=ProvenanceStatus(counts=counts, comparison=comparison),
    )

    changed_html = env.get_template(
        "includes/packaging/security/changed-provenance.html"
    ).render(release=release, request=request)
    assert 'href="https://github.com/foo/old"' in changed_html
    assert ">github.com/foo/old</a>" in changed_html
    assert 'href="https://gitlab.com/foo/new"' in changed_html
    assert ">gitlab.com/foo/new</a>" in changed_html
    assert "ci@example.iam.gserviceaccount.com" in changed_html
    assert 'href="https://gitlab.com/foo/new/blob/bbb//.gitlab-ci.yml"' in changed_html
    assert ">gitlab.com/foo/new/blob/bbb//.gitlab-ci.yml</a>" in changed_html

    inconsistent_html = env.get_template(
        "includes/packaging/security/inconsistent-provenance.html"
    ).render(release=release, request=request)
    assert "Repository/Account" in inconsistent_html
    assert 'href="https://gitlab.com/foo/new"' in inconsistent_html
    assert ">gitlab.com/foo/new</a>" in inconsistent_html
    assert "ci@example.iam.gserviceaccount.com" in inconsistent_html
    assert (
        'href="https://github.com/foo/old/blob/aaa/.github/workflows/release.yml"'
        in inconsistent_html
    )
    assert (
        ">github.com/foo/old/blob/aaa/.github/workflows/release.yml</a>"
        in inconsistent_html
    )
    assert (
        'href="https://gitlab.com/foo/new/blob/bbb//.gitlab-ci.yml"'
        in inconsistent_html
    )
