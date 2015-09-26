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
import certifi


class _Boto3Session(boto3.session.Session):

    def client(self, *args, **kwargs):
        # We have certifi installed, which causes botocore to use the newer
        # CA Bundle which does not have the 1024 bit roots that Amazon requires
        # so instead we'll override this so that it uses the old bundle when
        # talking to Amazon.
        if kwargs.get("verify") is None:
            kwargs["verify"] = certifi.old_where()

        return super().client(*args, **kwargs)


def aws_session_factory(context, request):
    kwargs = {}

    # If we've been given a specific region, then connect to that.
    if request.registry.settings.get("aws.region") is not None:
        kwargs["region_name"] = request.registry.settings["aws.region"]

    return _Boto3Session(
        aws_access_key_id=request.registry.settings["aws.key_id"],
        aws_secret_access_key=request.registry.settings["aws.secret_key"],
        **kwargs
    )


def includeme(config):
    config.register_service_factory(aws_session_factory, name="aws.session")
