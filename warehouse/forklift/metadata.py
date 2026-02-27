# SPDX-License-Identifier: Apache-2.0

import email.message
import email.utils
import string
import typing

import email_validator

from packaging.metadata import (
    _LIST_FIELDS,
    _RAW_TO_EMAIL_MAPPING,
    _STRING_FIELDS,
    InvalidMetadata,
    Metadata,
    RawMetadata,
    _parse_keywords,
    _parse_project_urls,
)
from packaging.requirements import InvalidRequirement, Requirement
from trove_classifiers import all_classifiers, deprecated_classifiers
from webob.multidict import MultiDict

from warehouse.utils import http

SUPPORTED_METADATA_VERSIONS = {"1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5"}

DYNAMIC_FIELDS = [
    "Platform",
    "Supported-Platform",
    "Summary",
    "Description",
    "Description-Content-Type",
    "Keywords",
    "Home-Page",  # Deprecated, but technically permitted by PEP 643
    "Download-Url",  # Deprecated, but technically permitted by PEP 643
    "Author",
    "Author-Email",
    "Maintainer",
    "Maintainer-Email",
    "License",
    "License-Expression",
    "License-File",
    "Classifier",
    "Requires-Dist",
    "Requires-Python",
    "Requires-External",
    "Project-Url",
    "Provides-Extra",
    "Provides-Dist",
    "Obsoletes-Dist",
    # Although the following are deprecated fields, they are technically
    # permitted as dynamic by PEP 643
    # https://github.com/pypa/setuptools/issues/4797#issuecomment-2589514950
    "Requires",
    "Provides",
    "Obsoletes",
    "Import-Name",  # Permitted as dynamic in PEP 794
    "Import-Namespace",  # Permitted as dynamic in PEP 794
]

# Mapping of fields on a Metadata instance to any limits on the length of that
# field. Fields without a limit will naturally be unlimited in length.
_LENGTH_LIMITS = {
    "summary": 512,
}


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

    # Validate the metadata using our custom rules, which we layer on top of the
    # built in rules to add PyPI specific constraints above and beyond what the
    # core metadata requirements are.
    _validate_metadata(metadata, backfill=backfill)

    return metadata


def _validate_metadata(metadata: Metadata, *, backfill: bool = False):
    # Add our own custom validations on top of the standard validations from
    # packaging.metadata.
    errors: list[InvalidMetadata] = []

    # We restrict the supported Metadata versions to the ones that we've implemented
    # support for. The metadata version is first validated by `packaging` thus adding a
    # version here does not make is supported unless it is supported by `packaging` as
    # well. See `packaging.metadata._VALID_METADATA_VERSIONS` for a list of the
    # supported versions.
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
                f"The use of local versions in '{metadata.version}' is not allowed.",
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
        if (addr := getattr(metadata, field)) is not None:
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
    for classifier in sorted(set(metadata.classifiers or []) - set(all_classifiers)):
        errors.append(
            InvalidMetadata("classifier", f"{classifier!r} is not a valid classifier.")
        )

    # Validate that no deprecated classifiers are being used.
    # NOTE: We only check this is we're not doing a backfill, because backfill
    #       operations may legitimately use deprecated classifiers.
    if not backfill:
        for classifier in sorted(
            set(metadata.classifiers or []) & deprecated_classifiers.keys()
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
        if (url := getattr(metadata, field)) is not None:
            if not http.is_valid_uri(url, require_authority=False):
                errors.append(
                    InvalidMetadata(
                        _RAW_TO_EMAIL_MAPPING.get(field, field),
                        f"{url!r} is not a valid url.",
                    )
                )

    # Validate the Project URL structure to ensure that we have real, valid,
    # values for both labels and urls.
    # TODO: Lift this up to packaging.metadata.
    for label, url in (metadata.project_urls or {}).items():
        if not label:
            errors.append(InvalidMetadata("project-url", "Must have a label"))
        elif len(label) > 32:
            errors.append(
                InvalidMetadata(
                    "project-url", f"{label!r} must be 32 characters or less."
                )
            )
        elif not url:
            errors.append(InvalidMetadata("project-url", "Must have a URL"))
        elif not http.is_valid_uri(url, require_authority=False):
            errors.append(InvalidMetadata("project-url", f"{url!r} is not a valid url"))

    # Validate that the *-Dist fields that packaging.metadata didn't validate are valid.
    # TODO: This probably should be pulled up into packaging.metadata.
    for field in {"provides_dist", "obsoletes_dist"}:
        if (value := getattr(metadata, field)) is not None:
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
        if (value := getattr(metadata, field)) is not None:
            for req in value:
                if req.url is not None:
                    errors.append(
                        InvalidMetadata(
                            _RAW_TO_EMAIL_MAPPING.get(field, field),
                            f"Can't have direct dependency: {req}",
                        )
                    )

    # Validate that any `dynamic` fields passed are in the allowed list
    # TODO: This probably should be lifted up to packaging.metadata
    for field in {"dynamic"}:
        if (value := getattr(metadata, field)) is not None:
            for key in value:
                if key not in map(str.lower, DYNAMIC_FIELDS):
                    errors.append(
                        InvalidMetadata(
                            _RAW_TO_EMAIL_MAPPING.get(field, field),
                            f"Dynamic field {key!r} is not a valid dynamic field.",
                        )
                    )

    # Ensure that License and License-Expression are mutually exclusive
    # See https://peps.python.org/pep-0639/#deprecate-license-field
    if metadata.license and metadata.license_expression:
        errors.append(
            InvalidMetadata(
                "license",
                (
                    "License is deprecated when License-Expression is present. "
                    "Only License-Expression should be present."
                ),
            )
        )

    # If we've collected any errors, then raise an ExceptionGroup containing them.
    if errors:
        raise ExceptionGroup("invalid metadata", errors)


# Map Form fields to RawMetadata
_override = {
    "platforms": "platform",
    "supported_platforms": "supported_platform",
    "license_files": "license_file",
    "import_names": "import_name",
    "import_namespaces": "import_namespace",
}
_FORM_TO_RAW_MAPPING = {_override.get(k, k): k for k in _RAW_TO_EMAIL_MAPPING}


def parse_form_metadata(data: MultiDict) -> Metadata:
    # We construct a RawMetadata using the form data, which we will later pass
    # to Metadata to get a validated metadata.
    #
    # NOTE: Form data is very similar to the email format where the only difference
    #       between a list and a single value is whether or not the same key is used
    #       multiple times. Thus, we will handle things in a similar way, always
    #       fetching things as a list and then determining what to do based on the
    #       field type and how many values we found.
    #
    #       In general, large parts of this have been taken directly from
    #       packaging.metadata and adjusted to work with form data.
    raw: dict[str, str | list[str] | dict[str, str]] = {}
    unparsed: dict[str, list[str]] = {}

    for name in frozenset(data.keys()):
        # We have to be lenient in the face of "extra" data, because the data
        # value here might contain unrelated form data, so we'll skip thing for
        # fields that aren't in our list of values.
        raw_name = _FORM_TO_RAW_MAPPING.get(name)
        if raw_name is None:
            continue

        # We use getall() here, even for fields that aren't multiple use,
        # because otherwise someone could have e.g. two Name fields, and we
        # would just silently ignore it rather than doing something about it.
        value = data.getall(name) or []

        # An empty string is invalid for all fields, treat it as if it wasn't
        # provided in the first place
        if value == [""]:
            continue

        # If this is one of our string fields, then we'll check to see if our
        # value is a list of a single item. If it is then we'll assume that
        # it was emitted as a single string, and unwrap the str from inside
        # the list.
        #
        # If it's any other kind of data, then we haven't the faintest clue
        # what we should parse it as, and we have to just add it to our list
        # of unparsed stuff.
        if raw_name in _STRING_FIELDS and len(value) == 1:
            raw[raw_name] = value[0]
        # If this is one of our list of string fields, then we can just assign
        # the value, since forms *only* have strings, and our getall() call
        # above ensures that this is a list.
        elif raw_name in _LIST_FIELDS:
            raw[raw_name] = value
        # Special Case: Keywords
        # The keywords field is implemented in the metadata spec as a str,
        # but it conceptually is a list of strings, and is serialized using
        # ", ".join(keywords), so we'll do some light data massaging to turn
        # this into what it logically is.
        elif raw_name == "keywords" and len(value) == 1:
            raw[raw_name] = _parse_keywords(value[0])
        # Special Case: Project-URL
        # The project urls is implemented in the metadata spec as a list of
        # specially-formatted strings that represent a key and a value, which
        # is fundamentally a mapping, however the email format doesn't support
        # mappings in a sane way, so it was crammed into a list of strings
        # instead.
        #
        # We will do a little light data massaging to turn this into a map as
        # it logically should be.
        elif raw_name == "project_urls":
            try:
                raw[raw_name] = _parse_project_urls(value)
            except KeyError:
                unparsed[name] = value
        # Nothing that we've done has managed to parse this, so it'll just
        # throw it in our unparsable data and move on.
        else:
            unparsed[name] = value

    # If we have any unparsed data, then we treat that as an error
    if unparsed:
        raise ExceptionGroup(
            "unparsed",
            [InvalidMetadata(key, f"{key!r} has invalid data") for key in unparsed],
        )

    # We need to cast our `raw` to a metadata, because a TypedDict only support
    # literal key names, but we're computing our key names on purpose, but the
    # way this function is implemented, our `TypedDict` can only have valid key
    # names.
    return Metadata.from_raw(typing.cast(RawMetadata, raw))


def normalize_project_url_label(label: str) -> str:
    # Normalize a Project-URL label according to the label normalization
    # rules in the "Well-Known Project URLs in Metadata" specification:
    # <https://packaging.python.org/en/latest/specifications/well-known-project-urls/#label-normalization>
    chars_to_remove = string.punctuation + string.whitespace
    removal_map = str.maketrans("", "", chars_to_remove)
    return label.translate(removal_map).lower()
