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

from .recaptcha import Service


def service_factory(handler, request):
    return Service(request)


def includeme(config):
    # yeah yeah, binding to a concrete implementation rather than an
    # interface. in a perfect world, this will never be offloaded to another
    # service. however, if it is, then we'll deal with the refactor then
    config.register_service_factory(service_factory, name="recaptcha")
