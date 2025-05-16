# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.forms import PreventHTMLTagsValidator
from warehouse.i18n import localize as _


class SubmitMalwareObservationForm(wtforms.Form):
    """Form to submit details about a Project with Malware"""

    inspector_link = wtforms.fields.URLField(
        validators=[
            wtforms.validators.Length(max=2000),
            wtforms.validators.Regexp(
                r"https://inspector\.pypi\.io/project/[^/]+/",
                message=_("Provide an Inspector link to specific lines of code."),
            ),
        ],
    )

    summary = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Length(min=10, max=2000),
            PreventHTMLTagsValidator(),
        ],
    )

    submit = wtforms.SubmitField()
