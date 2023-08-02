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

from pathlib import Path

import pytest

from jinja2 import Environment, FileSystemLoader

import warehouse

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
}


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
    dir_name = Path(warehouse.__path__[0]) / "templates"

    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
        ],
        cache_size=0,
    )

    env.filters.update(FILTERS)

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
    dir_name = Path(warehouse.__path__[0]) / "templates"

    env = Environment(
        loader=FileSystemLoader(dir_name),
        extensions=[
            "jinja2.ext.i18n",
            "warehouse.utils.html.ClientSideIncludeExtension",
            "warehouse.i18n.extensions.TrimmedTranslatableTagsExtension",
        ],
        cache_size=0,
    )

    env.filters.update(FILTERS)

    assert env.get_template(str(template))
