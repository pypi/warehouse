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


class ObservationKindEnum(str, enum.Enum):
    source: str
    subject: str
    short_desc: str

    description: str

    # Name = ("source:subject:description", "Friendly description")
    def __new__(cls, value: str, description: str):
        values = value.split(":")
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.source = values[0]
        obj.subject = values[1]
        obj.short_desc = values[2]

        obj.description = description

        return obj


class ObservationKind:
    class Account(ObservationKindEnum):
        IsMalicious = ("pypi_user_report:account:is_malicious", "It is malicious")
        IsSpam = ("pypi_user_report:account:is_spam", "It is spam")
        SomethingElse = ("pypi_user_report:account:something_else", "Something else")

    class Project(ObservationKindEnum):
        IsMalicious = ("pypi_user_report:project:is_malicious", "It is malicious")
        IsSpam = ("pypi_user_report:project:is_spam", "It is spam")
        SomethingElse = ("pypi_user_report:project:something_else", "Something else")

    class Release(ObservationKindEnum):
        IsMalicious = ("pypi_user_report:release:is_malicious", "It is malicious")
        IsSpam = ("pypi_user_report:release:is_spam", "It is spam")
        SomethingElse = ("pypi_user_report:release:something_else", "Something else")

    class File(ObservationKindEnum):
        IsMalicious = ("pypi_user_report:file:is_malicious", "It is malicious")
        IsSpam = ("pypi_user_report:file:is_spam", "It is spam")
        SomethingElse = ("pypi_user_report:file:something_else", "Something else")
