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

import enum


class StrLabelEnum(str, enum.Enum):
    """Base class for Enum with string value and display label."""

    label: str

    # Name = "value", _("Label")
    def __new__(cls, value: str, label: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj
