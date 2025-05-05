---
title: Organization Actions
---

# Operations
This section describes the actions that can be performed
within an organization account.

!!! note

    All actions assume an authorized user has logged into their account.

## Organization actions

#### Create an organization

*Actor: Any PyPI user*

* Click on **Your organization** in the left menu or the right drop down menu
* Enter the organization details under **Create new organization**
* Choose if the organization is a private organization or a community project
* Click on **Create**

If the organization being created is a corporate organization,
a billing page will appear. Enter the billing details.

Once the organization has been created, it will have to be
approved by the PyPI admin.
This usually takes <<TODO>> days.
Once the account request has been approved,
the user who created the account becomes the Owner of the organization.
The Owner will be able to manage the organization once it has been approved.

A user can create any number of organizations.

---

#### Add member to an organization

*Actor: Owner*

* Click on **Your organizatio**n
* Click on **Manage** for a specific organization
* Click on **People**
* Enter the username and assign the role for the user

The invited user will receive an email and will see an invitation
banner when they log into their account. The user will automatically
appear as a member in the organization if they accept the invitation.
The owners of the organization will receive an email notification
if the user declined the invitation.

The invited user should have an account in PyPI.
Invitations can be sent via username and not by email address.
There is no limit to the number of members within an organization.

---

#### Cancel user invitation

*Actor: Owner*

* Click on **Your organization**
* Click on **Manage** for a specific organization
* Click on **People**
* Click on **Revoke invite**
* Click on **Revoke invite** again

The user will receive an email that the invitation has been revoked.

---

#### Remove member from an organization
*Actor: Owner*

* Click on **Your organization**
* Click on **Manage** for a specific organization
* Click on **People**
* Click on **Remove** for a specific user
* Enter the username of the user and click on **Remove**

---

#### Assign a user role

*Actor: Owner*

* Click on **Your organizations**
* Click on **Manage** for a specific organization
* Click on **People**
* Assign a new role to a user who is a member of the organization.
The new role can be owner, manager, billing manager or member.
* Click on **Save**

A user can have only one role at any given time.
There can be multiple users with the same role.

---

#### Accept/Reject an invitation to join an organization

*Actor: Any user*

* Click on **Your organizations**
* Under Pending invitations, click on **Accept** or **Decline**

If the invitation has been accepted,
the organization will appear under Your organizations.
If the invitation has been declined, the Owners of the organization
will be notified by email.

---

#### Rename an organization account

*Actor: Owner*

* Click on **Your organizations**
* Click on **Manage** for a specific organization
* Click on **Settings**
* Scroll to the bottom of the page and click on
**Change organization account name**
* Enter the **New organization account name** and
**Current organization account name**
* Click on **Change organization account name**

The new name will be assigned only if there are no
other organizations with the same name.

---

#### Leave an organization

*Actor: Any member of the organization*

* Click on **Your organizations**
* Click on **Manage** for a specific organization
* Click on **People**
* Click on **Remove** next to your username in the list of users
* Enter your username and click on **Remove**

The Owners of the organization will receive an email notification.
The last Owner of the organization cannot leave the organization.
They will have to delete the organization.

---

#### Delete an organization account

*Actor: Owner*

* Click on **Your organizations**
* Click on **Manage** for a specific organization
* Click on **Settings**
* Scroll to the bottom of the page and click on **Delete organization**
* Enter the organization name and click on **Delete organization**

This action can be performed only if all the projects within an organization
have been assigned to a user.
The project history will be maintained.
