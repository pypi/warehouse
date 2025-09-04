# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.constants import (
    MAX_FILESIZE,
    MAX_PROJECT_SIZE,
    ONE_GIB,
    ONE_MIB,
    UPLOAD_LIMIT_CAP,
)


class SetUploadLimitForm(wtforms.Form):
    """
    Form for validating upload limit input in admin interface.

    Used by both project and organization admin views to ensure
    consistent validation of upload limits.
    """

    upload_limit = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
        ],
        filters=[lambda x: None if (x == "" or not x) else x],
    )

    def validate_upload_limit(self, field):
        """
        Validate upload limit value.

        - Empty string means remove the limit (use system default)
        - Must be a valid integer if provided
        - Must be between MIN and MAX allowed values
        """
        if field.data is None:
            # Already None from filter
            return

        try:
            limit_value = int(field.data)
        except (ValueError, TypeError):
            raise wtforms.ValidationError(
                "Upload limit must be a valid integer or empty"
            )

        # Check minimum (must be at least the system default)
        min_limit = MAX_FILESIZE // ONE_MIB
        if limit_value < min_limit:
            raise wtforms.ValidationError(
                f"Upload limit can not be less than {min_limit:0.1f}MiB"
            )

        # Check maximum (capped at 1GB)
        max_limit = UPLOAD_LIMIT_CAP // ONE_MIB
        if limit_value > max_limit:
            raise wtforms.ValidationError(
                f"Upload limit can not be greater than {max_limit:0.1f}MiB"
            )

        # Convert to bytes for storage
        field.data = limit_value * ONE_MIB


class SetTotalSizeLimitForm(wtforms.Form):
    """
    Form for validating total size limit input in admin interface.

    Used by both project and organization admin views to ensure
    consistent validation of total size limits.
    """

    total_size_limit = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
        ],
        filters=[lambda x: None if (x == "" or not x) else x],
    )

    def validate_total_size_limit(self, field):
        """
        Validate total size limit value.

        - Empty string means remove the limit (use system default)
        - Must be a valid integer if provided
        - Must be at least the system default
        """
        if field.data is None:
            # Already None from filter
            return

        try:
            limit_value = int(field.data)
        except (ValueError, TypeError):
            raise wtforms.ValidationError(
                "Total size limit must be a valid integer or empty"
            )

        # Check minimum (must be at least the system default)
        min_limit = MAX_PROJECT_SIZE // ONE_GIB
        if limit_value < min_limit:
            raise wtforms.ValidationError(
                f"Total organization size can not be less than {min_limit:0.1f}GiB"
            )

        # No maximum cap for total size (can be very large)

        # Convert to bytes for storage
        field.data = limit_value * ONE_GIB
