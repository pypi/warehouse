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

from pyramid.view import view_config

@view_config(route_name='security',
             renderer='security.html')
def security(request):
    return {
        'administrators': [
            {
                'name': 'Richard Jones',
                'keyid': '41C6E930',
                'fingerprint': '0145 FD2B 52E8 0A8E 329A 16C7 AC68 AC04 41C6 E930',
                'email': 'richard@python.org'
            },
            {
                'name': 'Donald Stufft',
                'keyid': '3372DCFA',
                'fingerprint': '7C6B 7C5D 5E2B 6356 A926 F04F 6E3C BCE9 3372 DCFA',
                'email': 'donald@python.org'
            },
            {
                'name': 'Martin von Löwis',
                'keyid': '7D9DC8D2',
                'fingerprint': 'CBC5 4797 8A39 64D1 4B9A B36A 6AF0 53F0 7D9D C8D2',
                'email': 'martin@v.loewis.de'
            }
        ]
    }
