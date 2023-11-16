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
from datetime import date

from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.attrs import make_repr
from warehouse.utils.db.types import bool_false


class Banner(db.Model):
    __tablename__ = "banners"
    __repr__ = make_repr("text")
    DEFAULT_FA_ICON = "fa-comment-alt"
    DEFAULT_BTN_LABEL = "See more"

    # internal name
    name: Mapped[str]

    # banner display configuration
    text: Mapped[str]
    link_url: Mapped[str]
    link_label: Mapped[str] = mapped_column(default=DEFAULT_BTN_LABEL)
    fa_icon: Mapped[str] = mapped_column(default=DEFAULT_FA_ICON)
    dismissable: Mapped[bool_false]

    # visibility control
    # TODO: Migrate to `warehouse.utils.db.types.bool_false` - triggers migration
    active: Mapped[bool] = mapped_column(default=False)
    end: Mapped[date]

    @property
    def is_live(self):
        # date.today is using the server timezone which is UTC
        return self.active and date.today() <= self.end
