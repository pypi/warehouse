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

import email.message
import email.utils
import os
import os.path
import zipfile

import email_validator

from packaging.metadata import Metadata, InvalidMetadata, _RAW_TO_EMAIL_MAPPING
from packaging.requirements import Requirement, InvalidRequirement
from packaging.utils import (
    parse_wheel_filename,
    canonicalize_name,
    canonicalize_version,
)
from trove_classifiers import classifiers, deprecated_classifiers
from webob.multidict import MultiDict

from warehouse.forklift.metadata.form import parse_form_metadata
from warehouse.utils import http


class InvalidArtifact(Exception):
    def __init__(self, reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reason = reason


def extract(path: os.PathLike) -> bytes | None:
    filename = os.path.basename(path)

    # TODO: Implement for sdists (requires Metadata 2.2)
    if filename.endswith(".whl"):
        name, version, _, _ = parse_wheel_filename(filename)
        version = canonicalize_version(version)

        with zipfile.ZipFile(path) as zfp:
            # Locate the dist-info directory.
            # Taken from pip's 'wheel_dist_info_dir utility function.
            #
            # TODO: We should probably eventually require that the dist-info directory
            #       is using normalized values instead of locating them like this.
            subdirs = {p.split("/", 1)[0] for p in zfp.namelist()}
            info_dirs = [s for s in subdirs if s.endswith(".dist-info")]

            if not info_dirs:
                raise InvalidArtifact(
                    f"Wheel {filename!r} does not contain a .dist-info directory",
                )

            if len(info_dirs) > 1:
                raise InvalidArtifact(
                    f"Wheel {filename!r} contains multiple .dist-info directories",
                )

            info_dir = info_dirs[0]

            # Validate that the name and version of the .dist-info directory
            # matches the name and version from the filename.
            #
            # NOTE: While normalization of filenames is currentlya bit of a mess,
            #       pretty much everything assumes that, at a minimum, the version
            #       isn't going to contain a - value, so we can rslit on that.
            dname, dversion = os.path.splitext(info_dir)[0].rsplit("-", 1)
            dname = canonicalize_name(dname)
            dversion = canonicalize_version(dversion)
            if name != dname or version != dversion:
                raise InvalidArtifact(
                    f"Wheel {filename!r} contains a .dist-info directory, "
                    "but it is for a different project or version.",
                )

            metadata_filename = f"{info_dir}/METADATA"

            try:
                metadata_contents = zfp.read(metadata_filename)
            except KeyError:
                raise InvalidArtifact(
                    f"Wheel {filename!r} does not contain a METADATA file",
                )

            return metadata_contents

    return None


class NoMetadataError(Exception):
    pass


def parse(
    content: bytes | None, *, form_data: MultiDict | None = None, backfill: bool = False
) -> Metadata:
    # We prefer to parse metadata from the content, which will typically come
    # from extracting a METADATA or PKG-INFO file from an artifact.
    if content is not None:
        metadata = Metadata.from_email(content)
    # If we have form data, then we'll fall back to parsing metadata out of that,
    # which should only ever happen for sdists prior to Metadata 2.2.
    elif form_data is not None:
        metadata = parse_form_metadata(form_data)
    # If we don't have contents or form data, then we don't have any metadata
    # and the only thing we can do is error.
    else:
        raise NoMetadataError

    # Validate the metadata using our custom rules, which we layer ontop of the
    # built in rules to add PyPI specific constraints above and beyond what the
    # core metadata requirements are.
    _validate_metadata(metadata, backfill=backfill)

    return metadata


SUPPORTED_METADATA_VERSIONS = {"1.0", "1.1", "1.2", "2.0", "2.1"}

SUPPORTED_DESCRIPTION_CONTENT_TYPES = {"text/plain", "text/x-rst", "text/markdown"}

SUPPORTED_DESCRIPTION_CONTENT_TYPE_VARIANTS = {
    "text/markdown": {"CommonMark", "GFM"},
}


def _validate_description_content_type(content_type: str) -> list[InvalidMetadata]:
    errors: list[InvalidMetadata] = []

    msg = email.message.EmailMessage()
    msg["content-type"] = content_type
    content_type, parameters = msg.get_content_type(), msg["content-type"].params

    # Make sure that our content type is one of our supported ones.
    if content_type not in SUPPORTED_DESCRIPTION_CONTENT_TYPES:
        errors.append(
            InvalidMetadata(
                "description-content-type",
                f"{content_type!r} is not a valid content type",
            )
        )

    # We only support UTF-8 charsets
    charset = parameters.get("charset")
    if charset and charset != "UTF-8":
        errors.append(
            InvalidMetadata(
                "description-content-type", f"{charset!r} is not a valid charset"
            )
        )

    # If we support variants for this content type, then check if the variant
    # is a supported one.
    supported_variants = SUPPORTED_DESCRIPTION_CONTENT_TYPE_VARIANTS.get(content_type)
    if supported_variants is not None:
        variant = parameters.get("variant")
        if variant and variant not in supported_variants:
            errors.append(
                InvalidMetadata(
                    "description-content-type",
                    f"{variant!r} is not a a supported variant for {content_type!r}",
                )
            )

    return errors


# Mapping of fields on a Metadata instance to any limits on the length of that
# field. Fields without a limit will naturally be unlimited in length.
_LENGTH_LIMITS = {
    "summary": 512,
}


def _validate_metadata(metadata: Metadata, *, backfill: bool = False):
    # Add our own custom validations ontop of the standard validations from
    # packaging.metadata.
    errors: list[InvalidMetadata] = []

    # We restrict the supported Metadata versions to the ones that we've implemented
    # support for.
    if metadata.metadata_version not in SUPPORTED_METADATA_VERSIONS:
        errors.append(
            InvalidMetadata(
                "metadata-version",
                f"{metadata.metadata_version!r} is not a valid metadata version",
            )
        )

    # We don't allow the use of the "local version" field when releasing to PyPI
    if metadata.version.local:
        errors.append(
            InvalidMetadata(
                "version",
                f"The use of local versions in {metadata.version!r} is not allowed.",
            )
        )

    # We put length constraints on some fields in order to prevent pathological
    # cases that don't really make sense in practice anyways.
    #
    # NOTE: We currently only support string fields.
    for field, limit in _LENGTH_LIMITS.items():
        value = getattr(metadata, field)
        if isinstance(value, str):
            if len(value) > limit:
                email_name = _RAW_TO_EMAIL_MAPPING.get(field, field)
                errors.append(
                    InvalidMetadata(
                        email_name,
                        f"{email_name!r} field must be {limit} characters or less.",
                    )
                )

    # We only support a fixed set of content types, charsets, and variants for
    # our description content type.
    errors.extend(_validate_description_content_type(metadata.description_content_type))

    # We require that the author and maintainer emails, if they're provided, are
    # valid RFC822 email addresses.
    # TODO: Arguably this should added to packaging.metadata, as the core metadata
    #       spec requires the use of RFC822 format for these fields, but since it
    #       doesn't do that currently, we'll add it here.
    #
    #       One thing that does make it hard for packaging.metadata to do this, is
    #       this validation isn't in the stdlib, and we use the email-validator
    #       package to implement it.
    for field in {"author_email", "maintainer_email"}:
        if addr := getattr(metadata, field):
            _, address = email.utils.parseaddr(addr)
            if address:
                try:
                    email_validator.validate_email(address, check_deliverability=False)
                except email_validator.EmailNotValidError as exc:
                    errors.append(
                        InvalidMetadata(
                            _RAW_TO_EMAIL_MAPPING.get(field, field),
                            f"{address!r} is not a valid email address: {exc}",
                        )
                    )

    # Validate that the classifiers are valid classifiers
    for classifier in sorted(set(metadata.classifiers) - classifiers):
        errors.append(
            InvalidMetadata("classifier", f"{classifier!r} is not a valid classifier.")
        )

    # Validate that no deprecated classifers are being used.
    # NOTE: We only check this is we're not doing a backfill, because backfill
    #       operations may legitimately use deprecated classifiers.
    if not backfill:
        for classifier in sorted(
            set(metadata.classifiers) & deprecated_classifiers.keys()
        ):
            deprecated_by = deprecated_classifiers[classifier]
            if deprecated_by:
                errors.append(
                    InvalidMetadata(
                        "classifier",
                        f"The classifier {classifier!r} has been deprecated, "
                        f"use one of {deprecated_by} instead.",
                    )
                )
            else:
                errors.append(
                    InvalidMetadata(
                        "classifier",
                        f"The classifier {classifier!r} has been deprecated.",
                    )
                )

    # Validate that URL fields are actually URLs
    # TODO: This is another one that it would be nice to lift this up to
    #       packaging.metadata
    for field in {"home_page", "download_url"}:
        if url := getattr(metadata, field):
            if not http.is_valid_uri(url, require_authority=False):
                errors.apend(
                    InvalidMetadata(
                        _RAW_TO_EMAIL_MAPPING.get(field, field),
                        f"{url!r} is not a valid url.",
                    )
                )

    # Validate the Project URL structure to ensure that we have real, valid,
    # values for both labels and urls.
    # TODO: Lift this up to packaging.metadata.
    for label, url in metadata.project_urls.items():
        if not label:
            errors.append(InvalidMetadata("project-url", f"Must have a label"))
        elif len(label) > 32:
            errors.append(
                InvalidMetadata(
                    "project-url", f"{label!r} must be 32 characters or less."
                )
            )

        if not url:
            errors.append(InvalidMetadata("project-url", f"Must have a URL"))
        elif not http.is_valid_uri(url, require_authority=False):
            errors.append(InvalidMetadata("project-url", f"{url!r} is not a valid url"))

    # Validate that the *-Dist fields that packaging.metadata didn't validate are valid.
    # TODO: This probably should be pulled up into packaging.metadata.
    for field in {"provides_dist", "obsoletes_dist"}:
        if value := getattr(metadata, field):
            for req_str in value:
                try:
                    req = Requirement(req_str)
                except InvalidRequirement as exc:
                    errors.append(
                        InvalidMetadata(
                            _RAW_TO_EMAIL_MAPPING.get(field, field),
                            f"{req_str!r} is invalid: {exc}",
                        )
                    )
                else:
                    # Validate that an URL isn't being listed.
                    # NOTE: This part should not be lifted to packaging.metadata
                    if req.url is not None:
                        errors.append(
                            InvalidMetadata(
                                _RAW_TO_EMAIL_MAPPING.get(field, field),
                                f"Can't have direct dependency: {req_str!r}",
                            )
                        )

    # Ensure that the *-Dist fields are not referencing any direct dependencies.
    # NOTE: Because packaging.metadata doesn't parse Provides-Dist and Obsoletes-Dist
    #       we skip those here and check that elsewhere. However, if packaging.metadata
    #       starts to parse those, then we can add them here.
    for field in {"requires_dist"}:
        if value := getattr(metadata, field):
            for req in value:
                if req.url is not None:
                    errors.append(
                        InvalidMetadata(
                            _RAW_TO_EMAIL_MAPPING.get(field, field),
                            f"Can't have direct dependency: {req}",
                        )
                    )

    # If we've collected any errors, then raise an ExceptionGroup containing them.
    if errors:
        raise ExceptionGroup("invalid metadata", errors)
