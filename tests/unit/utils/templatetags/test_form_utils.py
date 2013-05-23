# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from unittest import mock

from warehouse.utils.templatetags.form_utils import renderfield


def test_renderfield():
    # Setup a mock field object
    field = mock.NonCallableMock()
    widget = mock.Mock(return_value="Rendered Widget!")
    field.as_widget = widget

    # Attempt to render the field
    rendered = renderfield(field, **{"class": "my-class"})

    # Verify results
    assert rendered == "Rendered Widget!"
    assert widget.call_count == 1
    assert widget.call_args == (tuple(), {"attrs": {"class": "my-class"}})
