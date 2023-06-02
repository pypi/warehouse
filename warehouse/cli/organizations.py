# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import click

from warehouse.cli import warehouse


@warehouse.group()  # pragma: no branch
def organizations():
    """
    Group for organizations commands.
    """


@organizations.command()
@click.pass_obj
def migrate_unapproved_orgs_to_applications(config):
    """
    Creates OrganizationApplication objects for Organization objects
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.accounts.models import User
    from warehouse.db import Session
    from warehouse.events.tags import EventTag
    from warehouse.organizations.models import (
        Organization,
        OrganizationApplication,
        OrganizationNameCatalog,
        OrganizationRole,
    )

    session = Session(bind=config.registry["sqlalchemy.engine"])

    for organization in session.query(Organization):
        catalog_entry = (
            session.query(OrganizationNameCatalog)
            .filter_by(organization_id=organization.id)
            .one()
        )

        create_event = (
            session.query(Organization.Event)
            .filter_by(
                tag=EventTag.Organization.OrganizationCreate, source_id=organization.id
            )
            .one()
        )

        application = OrganizationApplication(
            name=organization.name,
            display_name=organization.display_name,
            orgtype=organization.orgtype,
            link_url=organization.link_url,
            description=organization.description,
            is_approved=organization.is_approved,
            submitted_by_id=create_event.additional["created_by_user_id"],
            submitted=create_event.time,
        )
        if organization.is_approved:
            application.organization = organization

        session.add(application)
        session.flush()  # flush the db now so application can ref organization

        if not organization.is_approved:
            session.query(OrganizationRole).filter_by(
                organization_id=organization.id
            ).delete()
            session.query(Organization.Event).filter_by(
                source_id=organization.id
            ).delete()
            session.query(User.Event).filter_by(
                source_id=create_event.additional["created_by_user_id"]
            ).filter_by(tag=EventTag.Account.OrganizationRoleAdd).filter(
                User.Event.additional.op("->>")("organization_name") == application.name
            ).filter(
                User.Event.additional.op("->>")("role_name") == "Owner"
            ).delete(
                synchronize_session="fetch"
            )
            session.delete(catalog_entry)
            session.delete(organization)

    session.commit()
