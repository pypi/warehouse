# SPDX-License-Identifier: Apache-2.0

from enum import StrEnum


class Permissions(StrEnum):
    """
    Permissions can be specified in an ACL (`__acl__`) or `@view_config(permission=...)`
    instead of using a string literal, minimizing the chance of typos.

    They are also disconnected from Principals (users, groups, etc.), so they can be
    used in a more generic way. For example, a permission could be used to allow a user
    to edit their own profile, or to allow a group to edit any profile.

    Naming should follow the format:
        <optional scope>:<resource>:<action>

    Where:
        scope: The scope of the permission, such as "admin", "manage", "api"
        resource: The resource being accessed
        action: The action being performed on the resource

    Keep the list alphabetized. Add spacing between logical groupings.
    """

    # Admin Permissions
    AdminBannerRead = "admin:banner:read"
    AdminBannerWrite = "admin:banner:write"

    AdminDashboardRead = "admin:dashboard:read"
    # TODO: This is broad, and could be replaced in the base template with more
    #       specific permissions per section. Other `__acl__`s need to be updated.
    AdminDashboardSidebarRead = "admin:dashboard-sidebar:read"

    AdminEmailsRead = "admin:emails:read"
    AdminEmailsWrite = "admin:emails:write"

    AdminFlagsRead = "admin:flags:read"
    AdminFlagsWrite = "admin:flags:write"

    AdminIpAddressesRead = "admin:ip-addresses:read"
    AdminJournalRead = "admin:journal:read"

    AdminMacaroonsRead = "admin:macaroons:read"
    AdminMacaroonsWrite = "admin:macaroons:write"

    AdminObservationsRead = "admin:observations:read"
    AdminObservationsWrite = "admin:observations:write"

    AdminOrganizationsRead = "admin:organizations:read"
    AdminOrganizationsSetLimit = "admin:organizations:set-limit"
    AdminOrganizationsWrite = "admin:organizations:write"
    AdminOrganizationsNameWrite = "admin:organizations:name:write"

    AdminProhibitedEmailDomainsRead = "admin:prohibited-email-domains:read"
    AdminProhibitedEmailDomainsWrite = "admin:prohibited-email-domains:write"

    AdminProhibitedProjectsRead = "admin:prohibited-projects:read"
    AdminProhibitedProjectsWrite = "admin:prohibited-projects:write"
    AdminProhibitedProjectsRelease = "admin:prohibited-projects:release"

    AdminProhibitedUsernameRead = "admin:prohibited-username:read"
    AdminProhibitedUsernameWrite = "admin:prohibited-username:write"

    AdminProjectsDelete = "admin:projects:delete"
    AdminProjectsRead = "admin:projects:read"
    AdminProjectsSetLimit = "admin:projects:set-limit"
    AdminProjectsWrite = "admin:projects:write"

    AdminRoleAdd = "admin:role:add"
    AdminRoleDelete = "admin:role:delete"
    AdminRoleUpdate = "admin:role:update"

    AdminSponsorsRead = "admin:sponsors:read"
    AdminSponsorsWrite = "admin:sponsors:write"

    AdminUsersRead = "admin:users:read"
    AdminUsersWrite = "admin:users:write"

    AdminUsersEmailWrite = "admin:users:email:write"
    AdminUsersAccountRecoveryWrite = "admin:users:account-recovery:write"

    # API Permissions
    APIEcho = "api:echo"
    APIObservationsAdd = "api:observations:add"

    # User Permissions
    Account2FA = "account:2fa"
    AccountAPITokens = "account:api-tokens"
    AccountManage = "account:manage"
    AccountManagePublishing = "account:manage-publishing"
    AccountVerifyEmail = "account:verify-email"
    AccountVerifyOrgRole = "account:verify-org-role"
    AccountVerifyProjectRole = "account:verify-project-role"

    # Projects Permissions
    ProjectsRead = "projects:read"
    ProjectsUpload = "projects:upload"
    ProjectsWrite = "projects:write"  # TODO: Worth splitting out ProjectDelete?

    # Organization Permissions
    OrganizationApplicationsManage = "organizations:applications:manage"
    OrganizationsManage = "organizations:manage"
    OrganizationsBillingManage = "organizations:billing:manage"
    OrganizationsRead = "organizations:read"
    OrganizationProjectsAdd = "organizations:projects:add"
    OrganizationProjectsRemove = "organizations:projects:remove"  # TODO: unused?
    OrganizationTeamsManage = "organizations:teams:manage"
    OrganizationTeamsRead = "organizations:teams:read"

    # Observer Permissions
    SubmitMalwareObservation = "observer:submit-malware-observation"
