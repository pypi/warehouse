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

import pretend

from warehouse.captcha import includeme, interfaces, recaptcha


def test_includeme_defaults_to_recaptcha():
    config = pretend.stub(
        registry=pretend.stub(settings={}),
        maybe_dotted=lambda i: i,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name: None
        ),
    )
    includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(
            recaptcha.Service.create_service,
            interfaces.ICaptchaService,
            name="recaptcha",
        ),
    ]
