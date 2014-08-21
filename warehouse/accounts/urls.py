# Copyright 2013 Donald Stufft
#
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

from werkzeug.routing import Rule, EndpointPrefix


urls = [
    EndpointPrefix("warehouse.accounts.views.", [
        Rule(
            "/account/login/",
            methods=["GET", "POST"],
            endpoint="login",
        ),
        Rule(
            "/account/logout/",
            methods=["GET", "POST"],
            endpoint="logout",
        ),
        Rule(
            "/account/register/",
            methods=["GET", "POST"],
            endpoint="register",
        ),
        Rule(
            "/account/confirm_account/<signed_value>",
            methods=["GET"],
            endpoint="confirm_account",
        ),
        Rule(
            "/user/<username>/",
            methods=["GET"],
            endpoint="user_profile",
        ),
    ]),
]
