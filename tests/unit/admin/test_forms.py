# SPDX-License-Identifier: Apache-2.0

from webob.multidict import MultiDict

from warehouse.admin.forms import (
    SetProjectCreateLimitForm,
    SetTotalSizeLimitForm,
    SetUploadLimitForm,
)


class TestSetUploadLimitForm:
    def test_validate_empty_string(self):
        """Test that empty string sets field data to None."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": ""}))
        assert form.validate()
        assert form.upload_limit.data is None
        # Verify the validator was called and returned early
        assert form.upload_limit.errors == []

    def test_validate_none(self):
        """Test that None value sets field data to None."""
        form = SetUploadLimitForm(MultiDict({}))
        assert form.validate()
        assert form.upload_limit.data is None
        # Verify the validator was called and returned early
        assert form.upload_limit.errors == []

    def test_validate_upload_limit_with_none_data(self):
        """Test validator directly with None data to cover early return."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": ""}))
        # The filter converts empty string to None
        assert form.upload_limit.data is None
        # Call validator directly to ensure the early return is covered
        form.validate_upload_limit(form.upload_limit)
        assert form.upload_limit.data is None

    def test_validate_valid_integer(self):
        """Test that valid integer is converted to bytes."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": "150"}))
        assert form.validate()
        assert form.upload_limit.data == 150 * 1024 * 1024  # 150 MiB in bytes

    def test_validate_invalid_value(self):
        """Test that non-integer value raises validation error."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": "not_a_number"}))
        assert not form.validate()
        assert (
            "Upload limit must be a valid integer or empty" in form.upload_limit.errors
        )

    def test_validate_below_minimum(self):
        """Test that value below minimum raises validation error."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": "50"}))  # < 100 MiB
        assert not form.validate()
        assert any(
            "Upload limit can not be less than" in error
            for error in form.upload_limit.errors
        )

    def test_validate_above_maximum(self):
        """Test that value above maximum raises validation error."""
        form = SetUploadLimitForm(MultiDict({"upload_limit": "2000"}))  # > 1024 MiB
        assert not form.validate()
        assert any(
            "Upload limit can not be greater than" in error
            for error in form.upload_limit.errors
        )


class TestSetTotalSizeLimitForm:
    def test_validate_empty_string(self):
        """Test that empty string sets field data to None."""
        form = SetTotalSizeLimitForm(MultiDict({"total_size_limit": ""}))
        assert form.validate()
        assert form.total_size_limit.data is None
        # Verify the validator was called and returned early
        assert form.total_size_limit.errors == []

    def test_validate_none(self):
        """Test that None value sets field data to None."""
        form = SetTotalSizeLimitForm(MultiDict({}))
        assert form.validate()
        assert form.total_size_limit.data is None
        # Verify the validator was called and returned early
        assert form.total_size_limit.errors == []

    def test_validate_total_size_limit_with_none_data(self):
        """Test validator directly with None data to cover early return."""
        form = SetTotalSizeLimitForm(MultiDict({"total_size_limit": ""}))
        # The filter converts empty string to None
        assert form.total_size_limit.data is None
        # Call validator directly to ensure the early return is covered
        form.validate_total_size_limit(form.total_size_limit)
        assert form.total_size_limit.data is None

    def test_validate_valid_integer(self):
        """Test that valid integer is converted to bytes."""
        form = SetTotalSizeLimitForm(MultiDict({"total_size_limit": "150"}))
        assert form.validate()
        assert (
            form.total_size_limit.data == 150 * 1024 * 1024 * 1024
        )  # 150 GiB in bytes

    def test_validate_invalid_value(self):
        """Test that non-integer value raises validation error."""
        form = SetTotalSizeLimitForm(MultiDict({"total_size_limit": "not_a_number"}))
        assert not form.validate()
        assert (
            "Total size limit must be a valid integer or empty"
            in form.total_size_limit.errors
        )

    def test_validate_below_minimum(self):
        """Test that value below minimum raises validation error."""
        form = SetTotalSizeLimitForm(MultiDict({"total_size_limit": "5"}))  # < 10 GiB
        assert not form.validate()
        assert any(
            "Total organization size can not be less than" in error
            for error in form.total_size_limit.errors
        )


class TestSetProjectCreateLimitForm:
    def test_validate_empty_count_clears_override(self):
        """Test that an empty count means clearing the override."""
        form = SetProjectCreateLimitForm(
            MultiDict(
                {
                    "project_create_limit_count": "",
                    "project_create_limit_period": "hour",
                }
            )
        )
        assert form.validate()
        assert form.limit_string is None

    def test_validate_missing_fields_clears_override(self):
        """Test that missing fields mean clearing the override."""
        form = SetProjectCreateLimitForm(MultiDict({}))
        assert form.validate()
        assert form.limit_string is None

    def test_validate_composes_limit_string(self):
        """Test that count and period compose into a rate limit string."""
        for period in ("hour", "day", "month"):
            form = SetProjectCreateLimitForm(
                MultiDict(
                    {
                        "project_create_limit_count": "5",
                        "project_create_limit_period": period,
                    }
                )
            )
            assert form.validate()
            assert form.limit_string == f"5 per {period}"

    def test_validate_rejects_zero_count(self):
        """Test that a count below 1 fails validation."""
        form = SetProjectCreateLimitForm(
            MultiDict(
                {
                    "project_create_limit_count": "0",
                    "project_create_limit_period": "hour",
                }
            )
        )
        assert not form.validate()
        assert any(
            "at least 1" in error for error in form.project_create_limit_count.errors
        )

    def test_validate_rejects_non_integer_count(self):
        """Test that a non-integer count fails validation."""
        form = SetProjectCreateLimitForm(
            MultiDict(
                {
                    "project_create_limit_count": "lots",
                    "project_create_limit_period": "hour",
                }
            )
        )
        assert not form.validate()

    def test_validate_rejects_unknown_period(self):
        """Test that a period outside the choices fails validation."""
        form = SetProjectCreateLimitForm(
            MultiDict(
                {
                    "project_create_limit_count": "5",
                    "project_create_limit_period": "fortnight",
                }
            )
        )
        assert not form.validate()
