# SPDX-License-Identifier: Apache-2.0

import click

from warehouse.cli import warehouse

# Survey URL constants
SURVEY_URLS = {
    "utilization_company": "https://forms.gle/CTy9LXzxqNRBJqy87",
    "utilization_community": "https://forms.gle/r4A7eXR3qSHLRJhE7",
    "no_utilization_company": "https://forms.gle/zXVZhXwwKhHWrsPo9",
    "no_utilization_community": "https://forms.gle/qG3nm1hFAmWDYRFcA",
}


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
def send_survey_emails(config, dry_run, limit):
    """
    Send survey emails to all organization members based on organization type
    and utilization status.
    """
    # Import here to avoid circular imports
    import functools
    import time

    import pyramid.scripting
    import transaction

    from sqlalchemy.orm import joinedload

    from warehouse.email import send_organization_survey_email
    from warehouse.organizations.models import Organization
    from warehouse.tasks import _get_task

    # Create a proper request using pyramid's scripting support
    env = pyramid.scripting.prepare(registry=config.registry)
    request = env["request"]
    session = request.db

    # Set up transaction manager for proper Celery task queueing
    request.tm = transaction.TransactionManager(explicit=True)
    request.tm.begin()

    # Add the task method to the request so we can enqueue Celery tasks
    celery_app = config.registry["celery.app"]
    request.task = functools.partial(_get_task, celery_app)

    # Add timings attribute that metrics service expects
    request.timings = {"new_request_start": time.time() * 1000}

    # Get all organizations
    orgs_query = (
        session.query(Organization)
        .filter(Organization.is_active.is_(True))
        .options(
            joinedload(Organization.users),
            joinedload(Organization.projects),
        )
    )

    if limit:
        orgs_query = orgs_query.limit(limit)

    organizations = orgs_query.all()

    click.echo(f"Processing {len(organizations)} organizations...")

    stats = {
        "total_orgs": 0,
        "total_emails": 0,
        "utilization_company": 0,
        "utilization_community": 0,
        "no_utilization_company": 0,
        "no_utilization_community": 0,
    }

    for org in organizations:
        stats["total_orgs"] += 1

        # Determine utilization status (has projects?)
        has_projects = len(org.projects) > 0

        # Determine organization type
        is_company = org.orgtype.value == "Company"

        # Select appropriate survey URL
        if has_projects and is_company:
            survey_url = SURVEY_URLS["utilization_company"]
            survey_type = "utilization_company"
        elif has_projects and not is_company:
            survey_url = SURVEY_URLS["utilization_community"]
            survey_type = "utilization_community"
        elif not has_projects and is_company:
            survey_url = SURVEY_URLS["no_utilization_company"]
            survey_type = "no_utilization_company"
        else:
            survey_url = SURVEY_URLS["no_utilization_community"]
            survey_type = "no_utilization_community"

        stats[survey_type] += 1

        # Get unique users for this organization
        users = set(org.users)

        click.echo(
            f"  Organization: {org.name} "
            f"(Type: {org.orgtype.value}, "
            f"Has Projects: {has_projects}, "
            f"Users: {len(users)})"
        )

        for user in users:
            stats["total_emails"] += 1

            if dry_run:
                click.echo(
                    f"    [DRY RUN] Would send {survey_type} survey to {user.username} "
                    f"({user.email}) for org {org.name}"
                )
            else:
                try:
                    send_organization_survey_email(
                        request,
                        user,
                        organization_name=org.name,
                        survey_url=survey_url,
                        organization_type=org.orgtype.value,
                        has_projects=has_projects,
                    )
                    click.echo(
                        f"    Queued {survey_type} survey to {user.username} "
                        f"({user.email})"
                    )
                except Exception as e:
                    click.echo(
                        f"    ERROR sending to {user.username}: {str(e)}", err=True
                    )

    # Print summary statistics
    click.echo("\nSummary:")
    click.echo(f"  Total organizations processed: {stats['total_orgs']}")
    click.echo(f"  Total emails to send: {stats['total_emails']}")
    click.echo(f"  Utilization + Company: {stats['utilization_company']}")
    click.echo(f"  Utilization + Community: {stats['utilization_community']}")
    click.echo(f"  No Utilization + Company: {stats['no_utilization_company']}")
    click.echo(f"  No Utilization + Community: {stats['no_utilization_community']}")

    if dry_run:
        click.echo("\nDRY RUN - No emails were actually sent")
    else:
        # Commit the transaction to actually enqueue the Celery tasks
        request.tm.commit()
        click.echo(f"\nSuccessfully queued {stats['total_emails']} emails")

    # Clean up the pyramid environment
    env["closer"]()
