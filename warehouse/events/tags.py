# SPDX-License-Identifier: Apache-2.0

import enum


class EventTagEnum(str, enum.Enum):
    """Base class for Enum representing Event tags.

    Tags can be broken into three colon-separated parts:
    1. source type
    2. subject type
    3. action

    For example, for event tag "project:role:add":
    1. "project" is the source type
    2. "role" is the subject type
    3. "add" is the action

    In some cases, the subject type can contain a colon:

    For example, for event tag "project:release:file:remove":
    1. "project" is the source type
    2. "release:file" is the subject type
    3. "remove" is the action

    If omitted, subject type is implied to be the same as source type.

    For example, for event tag "project:create":
    1. "project" is the source type
    2. "project" is also the subject type
    3. "create" is the action

    """

    source_type: str
    subject_type: str
    action: str

    # Name = "source_type:subject_type:action"
    def __new__(cls, value: str):
        values = value.split(":")
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.source_type = values[0]
        obj.subject_type = ":".join(values[1:-1]) or value[0]
        obj.action = values[-1]
        return obj


class EventTag:
    class Account(EventTagEnum):
        """Tags for User events."""

        # Name = "source_type:subject_type:action"
        APITokenAdded = "account:api_token:added"
        APITokenRemoved = "account:api_token:removed"
        APITokenRemovedLeak = "account:api_token:removed_leak"
        AccountCreate = "account:create"
        EmailAdd = "account:email:add"
        EmailPrimaryChange = "account:email:primary:change"
        EmailRemove = "account:email:remove"
        EmailReverify = "account:email:reverify"
        EmailVerified = "account:email:verified"
        LoginFailure = "account:login:failure"
        LoginSuccess = "account:login:success"
        OrganizationRoleAdd = "account:organization_role:add"
        OrganizationRoleChange = "account:organization_role:change"
        OrganizationRoleDeclineInvite = "account:organization_role:decline_invite"
        OrganizationRoleExpireInvite = "account:organization_role:expire_invite"
        OrganizationRoleInvite = "account:organization_role:invite"
        OrganizationRoleRemove = "account:organization_role:remove"
        OrganizationRoleRevokeInvite = "account:organization_role:revoke_invite"
        PasswordChange = "account:password:change"
        PasswordDisabled = "account:password:disabled"
        PasswordReset = "account:password:reset"
        PasswordResetAttempt = "account:password:reset:attempt"
        PasswordResetRequest = "account:password:reset:request"
        PendingOIDCPublisherAdded = "account:oidc:pending-publisher-added"
        PendingOIDCPublisherRemoved = "account:oidc:pending-publisher-removed"
        RecoveryCodesGenerated = "account:recovery_codes:generated"
        RecoveryCodesRegenerated = "account:recovery_codes:regenerated"
        RecoveryCodesUsed = "account:recovery_codes:used"
        RoleAdd = "account:role:add"
        RoleChange = "account:role:change"
        RoleDeclineInvite = "account:role:decline_invite"
        RoleInvite = "account:role:invite"
        RoleRemove = "account:role:remove"
        RoleRevokeInvite = "account:role:revoke_invite"
        TeamRoleAdd = "account:team_role:add"
        TeamRoleRemove = "account:team_role:remove"
        TwoFactorDeviceRemembered = "account:two_factor:device_remembered"
        TwoFactorMethodAdded = "account:two_factor:method_added"
        TwoFactorMethodRemoved = "account:two_factor:method_removed"
        EmailSent = "account:email:sent"
        AlternateRepositoryAdd = "account:alternate_repository:add"
        AlternateRepositoryDelete = "account:alternate_repository:delete"
        # The following tags are no longer used when recording events.
        # ReauthenticateFailure = "account:reauthenticate:failure"
        # RoleAccepted = "account:role:accepted"

    class Project(EventTagEnum):
        """Tags for Project events.

        Keep in sync with: warehouse/templates/manage/project/history.html
        """

        # Name = "source_type:subject_type:action"
        ShortLivedAPITokenAdded = "account:short_lived_api_token:added"
        APITokenAdded = "project:api_token:added"
        APITokenRemoved = "project:api_token:removed"
        OIDCPublisherAdded = "project:oidc:publisher-added"
        OIDCPublisherRemoved = "project:oidc:publisher-removed"
        OrganizationProjectAdd = "project:organization_project:add"
        OrganizationProjectRemove = "project:organization_project:remove"
        OwnersRequire2FADisabled = "project:owners_require_2fa:disabled"
        OwnersRequire2FAEnabled = "project:owners_require_2fa:enabled"
        ProjectArchiveEnter = "project:archive:enter"
        ProjectArchiveExit = "project:archive:exit"
        ProjectCreate = "project:create"
        ProjectQuarantineEnter = "project:quarantine:enter"
        ProjectQuarantineExit = "project:quarantine:exit"
        ReleaseAdd = "project:release:add"
        ReleaseRemove = "project:release:remove"
        ReleaseUnyank = "project:release:unyank"
        ReleaseYank = "project:release:yank"
        RoleAdd = "project:role:add"
        RoleChange = "project:role:change"
        RoleDeclineInvite = "project:role:decline_invite"
        RoleInvite = "project:role:invite"
        RoleRemove = "project:role:remove"
        RoleRevokeInvite = "project:role:revoke_invite"
        TeamProjectRoleAdd = "project:team_project_role:add"
        TeamProjectRoleChange = "project:team_project_role:change"
        TeamProjectRoleRemove = "project:team_project_role:remove"
        AlternateRepositoryAdd = "project:alternate_repository:add"
        AlternateRepositoryDelete = "project:alternate_repository:delete"
        # The following tags are no longer used when recording events.
        # RoleAccepted = "project:role:accepted"
        # RoleDelete = "project:role:delete"
        # ReleaseFileAdd = "project:release:file:add"
        # ReleaseFileRemove = "project:release:file:remove"

    class File(EventTagEnum):
        """Tags for File events.

        Keep in sync with: warehouse/templates/manage/project/history.html
        """

        FileAdd = "file:add"
        FileRemove = "file:remove"

    class Organization(EventTagEnum):
        """Tags for Organization events.

        Keep in sync with: warehouse/templates/manage/organization/history.html
        """

        # Name = "source_type:subject_type:action"
        CatalogEntryAdd = "organization:catalog_entry:add"
        OrganizationApprove = "organization:approve"
        OrganizationApplicationSubmit = "organization:application_submit"
        OrganizationCreate = "organization:create"
        OrganizationDecline = "organization:decline"
        OrganizationDelete = "organization:delete"
        OrganizationRename = "organization:rename"
        OrganizationProjectAdd = "organization:organization_project:add"
        OrganizationProjectRemove = "organization:organization_project:remove"
        OrganizationRoleAdd = "organization:organization_role:add"
        OrganizationRoleChange = "organization:organization_role:change"
        OrganizationRoleDeclineInvite = "organization:organization_role:decline_invite"
        OrganizationRoleExpireInvite = "organization:organization_role:expire_invite"
        OrganizationRoleInvite = "organization:organization_role:invite"
        OrganizationRoleRemove = "organization:organization_role:remove"
        OrganizationRoleRevokeInvite = "organization:organization_role:revoke_invite"
        TeamCreate = "organization:team:create"
        TeamDelete = "organization:team:delete"
        TeamRename = "organization:team:rename"
        TeamProjectRoleAdd = "organization:team_project_role:add"
        TeamProjectRoleChange = "organization:team_project_role:change"
        TeamProjectRoleRemove = "organization:team_project_role:remove"
        TeamRoleAdd = "organization:team_role:add"
        TeamRoleRemove = "organization:team_role:remove"

        OIDCPublisherAdded = "organization:oidc:publisher-added"
        OIDCPublisherRemoved = "organization:oidc:publisher-removed"
        PendingOIDCPublisherAdded = "organization:oidc:pending-publisher-added"
        PendingOIDCPublisherRemoved = "organization:oidc:pending-publisher-removed"

    class Team(EventTagEnum):
        """Tags for Organization events.

        Keep in sync with: warehouse/templates/manage/team/history.html
        """

        # Name = "source_type:subject_type:action"
        TeamCreate = "team:create"
        TeamDelete = "team:delete"
        TeamRename = "team:rename"
        TeamProjectRoleAdd = "team:team_project_role:add"
        TeamProjectRoleChange = "team:team_project_role:change"
        TeamProjectRoleRemove = "team:team_project_role:remove"
        TeamRoleAdd = "team:team_role:add"
        TeamRoleRemove = "team:team_role:remove"
