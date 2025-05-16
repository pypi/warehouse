# SPDX-License-Identifier: Apache-2.0

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
