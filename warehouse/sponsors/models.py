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

from sqlalchemy import Boolean, Column, Integer, String, Text

from warehouse import db
from warehouse.utils import readme
from warehouse.utils.attrs import make_repr


class Sponsor(db.Model):
    __tablename__ = "sponsors"
    __repr__ = make_repr("name")

    name = Column(String, nullable=False)
    service = Column(String)
    activity_markdown = Column(Text)

    link_url = Column(Text, nullable=False)
    color_logo_url = Column(Text, nullable=False)
    white_logo_url = Column(Text)

    # control flags
    is_active = Column(Boolean, default=False, nullable=False)
    footer = Column(Boolean, default=False, nullable=False)
    psf_sponsor = Column(Boolean, default=False, nullable=False)
    infra_sponsor = Column(Boolean, default=False, nullable=False)
    one_time = Column(Boolean, default=False, nullable=False)
    sidebar = Column(Boolean, default=False, nullable=False)

    # pythondotorg integration
    origin = Column(String, default="manual")
    level_name = Column(String)
    level_order = Column(Integer, default=0)
    slug = Column(String)

    @property
    def color_logo_img(self):
        return f'<img src="{ self.color_logo_url }" alt="{ self.name }" loading="lazy">'

    @property
    def white_logo_img(self):
        if not self.white_logo_url:
            return ""
        return (
            '<img class="sponsors__image" '
            + f'src="{ self.white_logo_url }" alt="{ self.name }" loading="lazy">'
        )

    @property
    def activity(self):
        """
        Render raw activity markdown as HTML
        """
        if not self.activity_markdown:
            return ""
        return readme.render(self.activity_markdown, "text/markdown")
