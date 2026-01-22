# SPDX-License-Identifier: Apache-2.0


def calc_accuracy(true_pos: int, false_pos: int) -> float | None:
    """Calculate accuracy rate from true/false positives."""
    resolved = true_pos + false_pos
    return round((true_pos / resolved) * 100, 1) if resolved > 0 else None


def classify_observation(actions: dict | None, related_id) -> str:
    """
    Classify an observation as true_positive, false_positive, or pending.

    Classification rules:
    - true_positive: has 'remove_malware' action OR project removed (related_id=None)
    - false_positive: has 'verdict_not_malware' action AND project still exists
    - pending: no verdict yet

    Note: If a project was marked 'not malware' but later removed for another reason
    (e.g., spam), we don't penalize the observer - they correctly identified a
    problematic project.
    """
    # If project was removed, observer correctly identified a problem
    if related_id is None:
        return "true_positive"

    if not actions:
        return "pending"

    has_not_malware = False
    for action_data in actions.values():
        action = action_data.get("action", "")
        if action == "remove_malware":
            return "true_positive"
        if action == "verdict_not_malware":
            has_not_malware = True

    return "false_positive" if has_not_malware else "pending"
