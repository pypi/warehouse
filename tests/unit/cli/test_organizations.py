# SPDX-License-Identifier: Apache-2.0

import pyramid.scripting
import transaction

import warehouse.email

from warehouse.cli import organizations


class FakeOwner:
    def __init__(self, username, email):
        self.username = username
        self.email = email


class FakeOrg:
    def __init__(self, name, owners, good_standing=False):
        self.name = name
        self.owners = owners
        self._good_standing = good_standing

    def is_in_good_standing(self):
        return self._good_standing


class FakeQuery:
    def __init__(self, orgs):
        self._orgs = orgs
        self.limited_to = None

    def filter(self, *args):
        return self

    def options(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, n):
        self.limited_to = n
        return self

    def all(self):
        if self.limited_to is not None:
            return self._orgs[: self.limited_to]
        return self._orgs


def _prepare_cli_env(mocker, orgs):
    query = FakeQuery(orgs)
    request = mocker.Mock()
    request.db.query.return_value = query
    env = {"request": request, "closer": mocker.Mock()}
    mocker.patch.object(pyramid.scripting, "prepare", return_value=env)
    tm = mocker.Mock()
    mocker.patch.object(transaction, "TransactionManager", return_value=tm)
    config = mocker.Mock(registry={"celery.app": mocker.Mock()})
    return config, request, tm, env


class TestSendSubscriptionRequiredEmails:
    def test_dry_run_sends_nothing(self, mocker, cli):
        delinquent = FakeOrg(
            "DelinquentOrg",
            owners=[
                FakeOwner("owner1", "owner1@example.com"),
                FakeOwner("owner2", "owner2@example.com"),
            ],
        )
        paying = FakeOrg(
            "PayingOrg", owners=[FakeOwner("o", "o@example.com")], good_standing=True
        )
        config, _, tm, env = _prepare_cli_env(mocker, [delinquent, paying])
        send = mocker.patch.object(
            warehouse.email, "send_organization_subscription_required_email"
        )

        result = cli.invoke(
            organizations.send_subscription_required_emails,
            ["--dry-run"],
            obj=config,
        )

        assert result.exit_code == 0
        assert "Found 1 active Company organizations" in result.output
        assert (
            "[DRY RUN] Would send subscription-required notice to owner1 "
            "(owner1@example.com) for org DelinquentOrg" in result.output
        )
        assert "owner2" in result.output
        assert "PayingOrg" not in result.output
        assert "DRY RUN - No emails were actually sent" in result.output
        send.assert_not_called()
        tm.commit.assert_not_called()
        env["closer"].assert_called_once_with()

    def test_sends_to_owners_and_commits(self, mocker, cli):
        org = FakeOrg(
            "DelinquentOrg", owners=[FakeOwner("owner1", "owner1@example.com")]
        )
        config, request, tm, env = _prepare_cli_env(mocker, [org])
        send = mocker.patch.object(
            warehouse.email, "send_organization_subscription_required_email"
        )

        result = cli.invoke(
            organizations.send_subscription_required_emails, [], obj=config
        )

        assert result.exit_code == 0
        send.assert_called_once_with(
            request, org.owners[0], organization_name="DelinquentOrg"
        )
        assert "Successfully queued 1 emails" in result.output
        tm.commit.assert_called_once_with()
        env["closer"].assert_called_once_with()

    def test_send_error_is_reported(self, mocker, cli):
        org = FakeOrg(
            "DelinquentOrg", owners=[FakeOwner("owner1", "owner1@example.com")]
        )
        config, _, _, _ = _prepare_cli_env(mocker, [org])
        mocker.patch.object(
            warehouse.email,
            "send_organization_subscription_required_email",
            side_effect=Exception("smtp exploded"),
        )

        result = cli.invoke(
            organizations.send_subscription_required_emails, [], obj=config
        )

        assert result.exit_code == 0
        assert "ERROR sending to owner1: smtp exploded" in result.output

    def test_org_without_owners_warns(self, mocker, cli):
        org = FakeOrg("OrphanOrg", owners=[])
        config, _, _, _ = _prepare_cli_env(mocker, [org])
        send = mocker.patch.object(
            warehouse.email, "send_organization_subscription_required_email"
        )

        result = cli.invoke(
            organizations.send_subscription_required_emails, [], obj=config
        )

        assert result.exit_code == 0
        assert "WARNING: OrphanOrg has no owners to notify" in result.output
        assert "Organizations with no owners: 1" in result.output
        send.assert_not_called()

    def test_limit_restricts_query(self, mocker, cli):
        orgs = [
            FakeOrg(f"Org{i}", owners=[FakeOwner(f"u{i}", f"u{i}@example.com")])
            for i in range(3)
        ]
        config, _, _, _ = _prepare_cli_env(mocker, [*orgs])
        mocker.patch.object(
            warehouse.email, "send_organization_subscription_required_email"
        )

        result = cli.invoke(
            organizations.send_subscription_required_emails,
            ["--dry-run", "--limit", "2"],
            obj=config,
        )

        assert result.exit_code == 0
        assert "Org0" in result.output
        assert "Org1" in result.output
        assert "Org2" not in result.output
