# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from webob.multidict import MultiDict

from warehouse.admin.forms import (
    SetProjectCreateRateLimitForm,
    SetTotalSizeLimitForm,
    SetUploadLimitForm,
)
from warehouse.constants import PROJECT_CREATE_RATELIMIT_CAP, RateLimitPeriod


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
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": ""})
        )
        assert form.validate()
        assert form.project_create_ratelimit_count.data is None

    def test_validate_none_clears_override(self):
        form = SetProjectCreateRateLimitForm(MultiDict({}))
        assert form.validate()
        assert form.project_create_ratelimit_count.data is None

    def test_validate_composes_count_and_period(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {
                    "project_create_ratelimit_count": "50",
                    "project_create_ratelimit_period": "hour",
                }
            )
        )
        assert form.validate()
        assert form.project_create_ratelimit_count.data == 50
        assert form.project_create_ratelimit_period.data is RateLimitPeriod.Hour

    def test_validate_defaults_to_hour_period(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": "5"})
        )
        assert form.validate()
        assert form.project_create_ratelimit_count.data == 5
        assert form.project_create_ratelimit_period.data is RateLimitPeriod.Hour

    def test_validate_below_minimum_count(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": "0"})
        )
        assert not form.validate()
        assert any(
            "Rate limit count must be at least 1" in error
            for error in form.project_create_ratelimit_count.errors
        )

    def test_validate_rejects_a_count_above_the_cap(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {
                    "project_create_ratelimit_count": str(
                        PROJECT_CREATE_RATELIMIT_CAP + 1
                    )
                }
            )
        )
        assert not form.validate()
        assert any(
            "must be at most" in error
            for error in form.project_create_ratelimit_count.errors
        )

    def test_validate_accepts_the_cap(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {"project_create_ratelimit_count": str(PROJECT_CREATE_RATELIMIT_CAP)}
            )
        )
        assert form.validate()

    def test_validate_rejects_unknown_period(self):
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {
                    "project_create_ratelimit_count": "5",
                    "project_create_ratelimit_period": "fortnight",
                }
            )
        )
        assert not form.validate()
        assert form.project_create_ratelimit_period.errors

    def test_apply_to_writes_both_columns(self):
        entity = SimpleNamespace(
            project_create_ratelimit_count=None,
            project_create_ratelimit_period=None,
            project_create_ratelimit_string=None,
        )
        form = SetProjectCreateRateLimitForm(
            MultiDict(
                {
                    "project_create_ratelimit_count": "12",
                    "project_create_ratelimit_period": "day",
                }
            )
        )
        assert form.validate()

        assert form.apply_to(entity) is None
        assert entity.project_create_ratelimit_count == 12
        assert entity.project_create_ratelimit_period is RateLimitPeriod.Day

    def test_apply_to_returns_the_replaced_limit(self):
        entity = SimpleNamespace(
            project_create_ratelimit_count=12,
            project_create_ratelimit_period=RateLimitPeriod.Day,
            project_create_ratelimit_string="12 per day",
        )
        form = SetProjectCreateRateLimitForm(
            MultiDict({"project_create_ratelimit_count": ""})
        )
        assert form.validate()

        assert form.apply_to(entity) == "12 per day"
        assert entity.project_create_ratelimit_count is None
        # Cleared overrides still carry a valid period.
        assert entity.project_create_ratelimit_period is RateLimitPeriod.Hour
