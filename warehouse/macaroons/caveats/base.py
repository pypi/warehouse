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


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier
        # TODO: Surface this failure reason to the user.
        # See: https://github.com/pypa/warehouse/issues/9018
        self.failure_reason = None

    def verify(self, predicate) -> bool:
        return False

    def __call__(self, predicate):
        return self.verify(predicate)
