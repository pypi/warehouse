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
# limitations under the License.import sys

import sys

from pip_api import parse_requirements

left, right = sys.argv[1:3]
left_reqs = parse_requirements(left).keys()
right_reqs = parse_requirements(right).keys()

extra_in_left = left_reqs - right_reqs
extra_in_right = right_reqs - left_reqs

if extra_in_left:
    for dep in sorted(extra_in_left):
        print(f"- {dep}")

if extra_in_right:
    for dep in sorted(extra_in_right):
        print(f"+ {dep}")

if extra_in_left or extra_in_right:
    sys.exit(1)
