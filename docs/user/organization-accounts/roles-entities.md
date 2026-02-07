---
title: Roles and Entities
---

# Roles and entities in an organization account

This section describes the various types of roles and
entities that can exist within an organization.

## Entities

* **Organization**: An entity that groups together users from an
organization and the packages they  publish and manage.
* **Team**: A subset of users within an organization that have been
assigned the same permission.
The permissions can be Maintainer or Owner of a project.
* **Member**: Each individual user in an organization is considered
to be a member of the organization. Members make up the team and organization.

## Roles

Each user is assigned a role within the organization. Depending on the role,
they have permission to carry out a set of operations.

### Organization roles

* **Owner**: An owner can manage members in an organization or a team,
assign roles to members, assign  permissions to a team,
manage projects and billing.

* **Manager**: A manager can manage a team, assign permissions for a
team and manage a project

* **Member**: A member can manage projects. By default, all users in an
organization are members  of the organization.

* **Billing manager**: A billing manager can manage billing details,
download invoices/receipts,
renew and cancel subscriptions for an organization

### Project roles

A team or individual user can manage a project as a collaborator.

* **Maintainer**: A collaborator assigned this role can
upload releases for a project

* **Owner**: A collaborator assigned this role can manage
the project and collaborators for the project

This table summarizes the roles and perimissions within an organization.

| Action | Member | Manager | Owner | Billing Manager |
| ---------------------------------- | ------ | ------ | ------ | ------ |
| View organization/teams            | &check;| &check;| &check;| &check;|
| Create/manage teams                | &#9746;| &check;| &check;| &#9746;|
| Invite/manage organization members | &#9746;| &#9746;| &check;| &#9746;|
| Delete the organization            | &#9746;| &#9746;| &check;| &#9746;|
| Manage organization billing        | &#9746;| &#9746;| &check;| &check;|
| Own/maintain specific projects     | &check;| &check;| &check;| &#9746;|
| Create new projects                | &#9746;| &check;| &check;| &#9746;|
| Delete projects                    | &#9746;| &#9746;| &check;| &#9746;|
