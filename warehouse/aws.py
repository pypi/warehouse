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

import boto3.session


def aws_session_factory(context, request):
    kwargs = {}

    # If we've been given a specific region, then connect to that.
    if request.registry.settings.get("aws.region") is not None:
        kwargs["region_name"] = request.registry.settings["aws.region"]

    return boto3.session.Session(
        aws_access_key_id=request.registry.settings["aws.key_id"],
        aws_secret_access_key=request.registry.settings["aws.secret_key"],
        **kwargs
    )


def includeme(config):
    config.register_service_factory(aws_session_factory, name="aws.session")
