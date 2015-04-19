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


from warehouse import views


class TestSecurity:

    def test_security(self, request):
        dictionary = views.security(request)
        assert len(dictionary) == 1

        assert 'administrators' in dictionary
        administrators = dictionary['administrators']
        assert len(administrators) > 0

        for administrator in administrators:
            assert 'name' in administrator
            assert 'keyid' in administrator
            assert 'fingerprint' in administrator
            assert 'email' in administrator
