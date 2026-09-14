---
title: Managing Project Owners
---

# Managing Project Owners

## Collaborator roles

PyPI provides two distinct roles for project collaborators, each with specific permissions:

* **Maintainer:** A maintainer can upload new releases for a package. However, they are not permitted to add or remove other collaborators, nor can they delete project files, releases, or the entire project.  
* **Owner:** An owner possesses full administrative control over a project. They can upload releases, add or remove other owners and maintainers, and have the authority to delete project files, releases, or the project itself.

## Managing collaborators

Only current project owners have the ability to manage collaborators.

### Adding a collaborator

To add a new owner or maintainer to your project:

1. Log in to your PyPI account  
2. Navigate to the "Your Projects" section  
3. Select the desired project  
4. Click on "Manage"  
5. In the left sidebar, select "Collaborators"  
6. Enter the PyPI username of the person you wish to add  
7. Select either "Owner" or "Maintainer" as their role  
8. Click "Add"  
9. Enter your password (PyPI requires you to re-enter your password before performing sensitive actions)

**Granting owner status to another user gives them full administrative rights to your project.** A new owner will have the ability to remove you from the project entirely. Only grant ownership to individuals you trust completely.

### Removing a collaborator

To remove a collaborator from your project:

1. Follow steps 1-5 above  
2. You will see a list of current collaborators  
3. Click the "Remove" button next to the username of the collaborator you wish to remove  
4. Enter your password (PyPI requires you to re-enter your password before performing sensitive actions)

Note: You can remove your own ownership of a project, but only if there are other owners remaining.

## Transferring project ownership

To transfer ownership of a project to another user, you should add the new user as an owner. Once the new owner has been added, they can then remove your ownership if you wish to no longer be associated with the project.

## Becoming an owner or maintainer

Only the current owners of a project have the ability to add new owners or maintainers. If you need to request ownership, you should contact the current owner(s) of the project directly. Many project owners provide their contact details in the 'Author' field of the 'Meta' details on the project page.
