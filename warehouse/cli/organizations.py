# SPDX-License-Identifier: Apache-2.0

import time

import click
import pyramid.scripting
import transaction

from sqlalchemy.orm import joinedload

from warehouse.cli import warehouse


@warehouse.group()
def organizations():
    """
    Manage operations for organizations.
    """


@organizations.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be sent without actually sending emails",
)
@click.option(
    "--limit",
    type=int,
    help="Limit the number of organizations to process (useful for testing)",
)
@click.pass_obj
def send_subscription_required_emails(config, dry_run, limit):
    """
    Email owners of active Company organizations that have no active
    subscription and no active manual activation, reminding them that
    continued use requires purchasing at least one seat.
    """
    # avoid circular imports
    from warehouse.email import send_organization_subscription_required_email
    from warehouse.organizations.models import Organization, OrganizationType

    env = pyramid.scripting.prepare(registry=config.registry)
    request = env["request"]
    session = request.db

    request.tm = transaction.TransactionManager(explicit=True)
    request.tm.begin()
    request.timings = {"new_request_start": time.time() * 1000}

    orgs_query = (
        session.query(Organization)
        .filter(
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
        )
        .options(
            joinedload(Organization.subscriptions),
            joinedload(Organization.manual_activation),
        )
        .order_by(Organization.name)
    )

    if limit:
        orgs_query = orgs_query.limit(limit)

    candidates = [org for org in orgs_query.all() if not org.is_in_good_standing()]

    click.echo(
        f"Found {len(candidates)} active Company organizations "
        "without an active subscription..."
    )

    stats = {
        "total_orgs": 0,
        "total_emails": 0,
        "orgs_without_owners": 0,
    }

    for org in candidates:
        stats["total_orgs"] += 1

        owners = org.owners

        click.echo(f"  Organization: {org.name} (Owners: {len(owners)})")

        if not owners:
            stats["orgs_without_owners"] += 1
            click.echo(f"    WARNING: {org.name} has no owners to notify", err=True)
            continue

        for user in owners:
            stats["total_emails"] += 1

            if dry_run:
                click.echo(
                    f"    [DRY RUN] Would send subscription-required notice to "
                    f"{user.username} ({user.email}) for org {org.name}"
                )
            else:
                try:
                    send_organization_subscription_required_email(
                        request,
                        user,
                        organization_name=org.name,
                    )
                    click.echo(
                        f"    Queued subscription-required notice to "
                        f"{user.username} ({user.email})"
                    )
                except Exception as e:  # noqa: BLE001 - keep the batch going
                    click.echo(f"    ERROR sending to {user.username}: {e!s}", err=True)

    click.echo("\nSummary:")
    click.echo(f"  Organizations needing a subscription: {stats['total_orgs']}")
    click.echo(f"  Organizations with no owners: {stats['orgs_without_owners']}")
    click.echo(f"  Total emails to send: {stats['total_emails']}")

    if dry_run:
        click.echo("\nDRY RUN - No emails were actually sent")
    else:
        request.tm.commit()
        click.echo(f"\nSuccessfully queued {stats['total_emails']} emails")

    env["closer"]()
