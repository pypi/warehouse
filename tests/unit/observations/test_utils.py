# SPDX-License-Identifier: Apache-2.0
import pytest

from warehouse.observations import utils


class TestCalcAccuracy:
    """Tests for the calc_accuracy helper function."""

    @pytest.mark.parametrize(
        ("true_pos", "false_pos", "expected"),
        [
            (0, 0, None),  # No resolved = None
            (1, 0, 100.0),  # All true positives
            (0, 1, 0.0),  # All false positives
            (3, 1, 75.0),  # 3/4 = 75%
            (1, 1, 50.0),  # 50%
            (7, 3, 70.0),  # 7/10 = 70%
        ],
    )
    def test_accuracy_calculation(self, true_pos, false_pos, expected):
        assert utils.calc_accuracy(true_pos, false_pos) == expected


class TestClassifyObservation:
    """Tests for the classify_observation helper function."""

    @pytest.mark.parametrize(
        ("actions", "related_id", "expected"),
        [
            # No actions - project exists = pending
            (None, "some-uuid", "pending"),
            ({}, "some-uuid", "pending"),
            # No actions - project removed = true positive (they flagged a problem)
            (None, None, "true_positive"),
            ({}, None, "true_positive"),
            # Remove malware action = true positive
            (
                {123: {"action": "remove_malware", "actor": "admin"}},
                "some-uuid",
                "true_positive",
            ),
            # Also works with string keys (how actions are typically stored)
            ({"1": {"action": "remove_malware"}}, "some-id", "true_positive"),
            # Verdict not malware = false positive (project still exists)
            (
                {123: {"action": "verdict_not_malware", "actor": "admin"}},
                "some-uuid",
                "false_positive",
            ),
            ({"1": {"action": "verdict_not_malware"}}, "some-id", "false_positive"),
            # Other/unknown actions = pending
            (
                {123: {"action": "some_other_action", "actor": "admin"}},
                "some-uuid",
                "pending",
            ),
            ({"1": {"action": "some_other_action"}}, "some-id", "pending"),
            # Project removed takes precedence over any action
            # (observer correctly identified a problematic project)
            (
                {123: {"action": "remove_malware", "actor": "admin"}},
                None,
                "true_positive",
            ),
            (
                {123: {"action": "verdict_not_malware", "actor": "admin"}},
                None,
                "true_positive",
            ),
            (
                {123: {"action": "some_other_action", "actor": "admin"}},
                None,
                "true_positive",
            ),
            # remove_malware takes precedence over verdict_not_malware
            (
                {
                    123: {"action": "verdict_not_malware", "actor": "admin"},
                    124: {"action": "remove_malware", "actor": "admin"},
                },
                "some-uuid",
                "true_positive",
            ),
            (
                {
                    "1": {"action": "verdict_not_malware"},
                    "2": {"action": "remove_malware"},
                },
                "some-id",
                "true_positive",
            ),
        ],
    )
    def test_classify_observation(self, actions, related_id, expected):
        assert utils.classify_observation(actions, related_id) == expected
