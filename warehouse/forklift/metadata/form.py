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


import wtforms
import wtforms.validators

from packaging.metadata import Metadata, RawMetadata
from webob.multidict import MultiDict

from warehouse import forms

_error_message_order = ["metadata_version", "name", "version"]


class ListField(wtforms.Field):
    def process_formdata(self, valuelist):
        self.data = [v.strip() for v in valuelist if v.strip()]


# TODO: Eventually this whole validation thing should move to the packaging
#       library and we should just call that. However until PEP 426 is done
#       that library won't have an API for this.
class MetadataForm(forms.Form):
    # Identity Project and Release
    name = wtforms.StringField(
        description="Name",
        validators=[
            wtforms.validators.InputRequired(),
        ],
    )
    version = wtforms.StringField(
        description="Version",
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Regexp(
                r"^(?!\s).*(?<!\s)$",
                message="Can't have leading or trailing whitespace.",
            ),
        ],
    )

    # Additional Release metadata
    summary = wtforms.StringField(
        description="Summary",
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Length(max=512),
            wtforms.validators.Regexp(
                r"^.+$",  # Rely on the fact that . doesn't match a newline.
                message="Use a single line only.",
            ),
        ],
    )
    description = wtforms.StringField(
        description="Description", validators=[wtforms.validators.Optional()]
    )
    author = wtforms.StringField(
        description="Author", validators=[wtforms.validators.Optional()]
    )
    description_content_type = wtforms.StringField(
        description="Description-Content-Type",
        validators=[wtforms.validators.Optional()],
    )
    author_email = wtforms.StringField(
        description="Author-email",
        validators=[wtforms.validators.Optional()],
    )
    maintainer = wtforms.StringField(
        description="Maintainer", validators=[wtforms.validators.Optional()]
    )
    maintainer_email = wtforms.StringField(
        description="Maintainer-email",
        validators=[wtforms.validators.Optional()],
    )
    license = wtforms.StringField(
        description="License", validators=[wtforms.validators.Optional()]
    )
    keywords = wtforms.StringField(
        description="Keywords", validators=[wtforms.validators.Optional()]
    )
    classifiers = ListField(
        description="Classifier",
        validators=[],
    )
    platform = wtforms.StringField(
        description="Platform", validators=[wtforms.validators.Optional()]
    )

    # URLs
    home_page = wtforms.StringField(
        description="Home-Page",
        validators=[wtforms.validators.Optional(), forms.URIValidator()],
    )
    download_url = wtforms.StringField(
        description="Download-URL",
        validators=[wtforms.validators.Optional(), forms.URIValidator()],
    )

    # Dependency Information
    requires_python = wtforms.StringField(
        description="Requires-Python",
        validators=[wtforms.validators.Optional()],
    )

    # Legacy dependency information
    requires = ListField(validators=[wtforms.validators.Optional()])
    provides = ListField(validators=[wtforms.validators.Optional()])
    obsoletes = ListField(validators=[wtforms.validators.Optional()])

    # Newer dependency information
    requires_dist = ListField(
        description="Requires-Dist",
        validators=[wtforms.validators.Optional()],
    )
    provides_dist = ListField(
        description="Provides-Dist",
        validators=[wtforms.validators.Optional()],
    )
    obsoletes_dist = ListField(
        description="Obsoletes-Dist",
        validators=[wtforms.validators.Optional()],
    )
    requires_external = ListField(
        description="Requires-External",
        validators=[wtforms.validators.Optional()],
    )

    # Newer metadata information
    project_urls = ListField(
        description="Project-URL",
        validators=[wtforms.validators.Optional()],
    )


def parse_form_metadata(data: MultiDict) -> Metadata:
    # We construct a RawMetdata using the form data, which we will later pass
    # to Metadata to get a validated metadata.
    #
    # NOTE: Form data is very similiar to the email format where the only difference
    #       between a list and a single value is whether or not the same key is used
    #       multiple times. Thus we will handle things in a similiar way, always fetching
    #       things as a list and then determining what to do based on the field type and
    #       how many values we found.
    #
    #       In general, large parts of this have been taken directly from packaging.metadata
    #       and adjusted to work with form data.

    raw = RawMetadata(
        metadata_version="",
    )
