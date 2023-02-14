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


def split_and_strip_keywords(keyword_input: str) -> list[str]:
    """
    Split keywords on commas and strip whitespace, remove empties.
    Useful to cleanse user input prior to storing in Release.keywords_array.
    """
    return [keyword.strip() for keyword in keyword_input.split(",") if keyword.strip()]
