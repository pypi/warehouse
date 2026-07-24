# SPDX-License-Identifier: Apache-2.0

from webob.multidict import MultiDict

from warehouse.admin.forms import (
    SetProjectCreateRateLimitForm,
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


class TestSetProjectCreateRateLimitForm:
    def test_validate_empty_clears_override(self):
        """An empty count clears the override (composed string is None)."""
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": ""})
        )
        assert form.validate()
        assert form.project_create_ratelimit_string is None

    def test_validate_none_clears_override(self):
        """A missing count clears the override (composed string is None)."""
        form = SetProjectCreateRateLimitForm(MultiDict({}))
        assert form.validate()
        assert form.project_create_ratelimit_string is None

    def test_validate_composes_count_and_period(self):
        """A count + period compose into a `limits`-syntax string."""
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {
                    "project_create_ratelimit_count": "200",
                    "project_create_ratelimit_period": "hour",
                }
            )
        )
        assert form.validate()
        assert form.project_create_ratelimit_string == "200 per hour"

    def test_validate_defaults_to_hour_period(self):
        """The period field defaults to "hour" when not submitted."""
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": "5"})
        )
        assert form.validate()
        assert form.project_create_ratelimit_string == "5 per hour"

    def test_validate_below_minimum_count(self):
        """A count below 1 raises a validation error."""
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": "0"})
        )
        assert not form.validate()
        assert any(
            "Rate limit count must be at least 1" in error
            for error in form.project_create_ratelimit_count.errors
        )
