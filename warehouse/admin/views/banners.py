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

from pyramid.view import view_config

from warehouse.banners.models import Banner
from warehouse.forms import Form, URIValidator


@view_config(
    route_name="admin.banner.list",
    renderer="admin/banners/list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def banner_list(request):
    banners = request.db.query(Banner).order_by(Banner.begin.desc()).all()
    return {"banners": banners}


class BannerForm(Form):
    name = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=100),
            wtforms.validators.DataRequired(),
        ],
    )
    text = wtforms.fields.StringField(
        validators=[
            wtforms.validators.Length(max=280),
            wtforms.validators.DataRequired(),
        ],
    )
    link_url = wtforms.fields.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            URIValidator(),
        ]
    )
    begin = wtforms.fields.DateField(validators=[wtforms.validators.DataRequired()])
    end = wtforms.fields.DateField(validators=[wtforms.validators.DataRequired()])

    def validate(self, *args, **kwargs):
        if not super().validate(*args, **kwargs):
            return False

        begin, end = self.begin.data, self.end.data
        if begin > end:
            self.begin.errors.append("Begin date must be lower than end date")
            self.end.errors.append("End date must be greater than begin date")
            return False

        return True
