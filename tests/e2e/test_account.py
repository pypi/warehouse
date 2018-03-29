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

from urllib.parse import urljoin


def test_register_password_strength(selenium, base_url):
    register_url = urljoin(base_url, 'account/register')
    selenium.get(register_url)
    new_password = selenium.find_element_by_id('new_password')
    new_password.send_keys('foo')
    assert selenium.find_element_by_xpath(
        '//span[@class="password-strength__gauge password-strength__gauge--0"]'
    )
    assert selenium.find_element_by_xpath(
        '//li[text()="Passwords do not match"]')
    assert selenium.find_element_by_xpath(
        '//input[@type="submit"]').get_attribute('disabled')
