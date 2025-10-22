# SPDX-License-Identifier: Apache-2.0


def includeme(config):
    # We need to get the value of the Warehouse and Forklift domains, we'll use
    # these to segregate the Warehouse routes from the Forklift routes until
    # Forklift is properly split out into it's own project.
    warehouse = config.get_settings().get("warehouse.domain")

    # General Admin pages
    config.add_route("admin.dashboard", "/admin/", domain=warehouse)

    # Organization related Admin pages
    config.add_route(
        "admin.organization.list", "/admin/organizations/", domain=warehouse
    )
    config.add_route(
        "admin.organization.detail",
        "/admin/organizations/{organization_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.rename",
        "/admin/organizations/{organization_id}/rename/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.add_role",
        "/admin/organizations/{organization_id}/add_role/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.update_role",
        "/admin/organizations/{organization_id}/update_role/{role_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.delete_role",
        "/admin/organizations/{organization_id}/delete_role/{role_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.add_manual_activation",
        "/admin/organizations/{organization_id}/add_manual_activation/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.update_manual_activation",
        "/admin/organizations/{organization_id}/update_manual_activation/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.delete_manual_activation",
        "/admin/organizations/{organization_id}/delete_manual_activation/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.set_upload_limit",
        "/admin/organizations/{organization_id}/set_upload_limit/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.set_total_size_limit",
        "/admin/organizations/{organization_id}/set_total_size_limit/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.add_oidc_issuer",
        "/admin/organizations/{organization_id}/oidc-issuers/add/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization.delete_oidc_issuer",
        "/admin/organizations/{organization_id}/oidc-issuers/{issuer_id}/delete/",
        domain=warehouse,
    )

    config.add_route(
        "admin.organization_application.list",
        "/admin/organization_applications/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.detail",
        "/admin/organization_applications/{organization_application_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.approve",
        "/admin/organization_applications/{organization_application_id}/approve/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.requestmoreinfo",
        (
            "/admin/organization_applications/{organization_application_id}"
            "/requestmoreinfo/"
        ),
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.defer",
        "/admin/organization_applications/{organization_application_id}/defer/",
        domain=warehouse,
    )
    config.add_route(
        "admin.organization_application.decline",
        "/admin/organization_applications/{organization_application_id}/decline/",
        domain=warehouse,
    )

    # User related Admin pages
    config.add_route("admin.user.list", "/admin/users/", domain=warehouse)
    config.add_route(
        "admin.user.detail",
        "/admin/users/{username}/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.submit_email",
        "/admin/users/{username}/emails/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.add_email",
        "/admin/users/{username}/add_email/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.email_domain_check",
        "/admin/users/{username}/email_domain_check/",
        factory="warehouse.accounts.models:UserFactory",
        domain=warehouse,
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.delete_email",
        "/admin/users/{username}/delete_email/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.delete",
        "/admin/users/{username}/delete/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.freeze",
        "/admin/users/{username}/freeze/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.reset_password",
        "/admin/users/{username}/reset_password/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.account_recovery.initiate",
        "/admin/users/{username}/account_recovery/initiate/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.account_recovery.cancel",
        "/admin/users/{username}/account_recovery/cancel/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.account_recovery.complete",
        "/admin/users/{username}/account_recovery/complete/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.burn_recovery_codes",
        "/admin/users/{username}/burn_recovery_codes/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.quarantine_projects",
        "/admin/users/{username}/quarantine_projects/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )
    config.add_route(
        "admin.user.clear_quarantine_projects",
        "/admin/users/{username}/clear_quarantine_projects/",
        domain=warehouse,
        factory="warehouse.accounts.models:UserFactory",
        traverse="/{username}",
    )

    # Macaroon related Admin pages
    config.add_route(
        "admin.macaroon.decode_token", "/admin/token/decode", domain=warehouse
    )
    config.add_route(
        "admin.macaroon.detail", "/admin/macaroons/{macaroon_id}", domain=warehouse
    )
    config.add_route(
        "admin.macaroon.delete",
        "/admin/macaroons/{macaroon_id}/delete",
        domain=warehouse,
    )

    # IP Address related Admin pages
    config.add_route("admin.ip_address.list", "/admin/ip-addresses/", domain=warehouse)
    config.add_route(
        "admin.ip_address.detail",
        "/admin/ip-addresses/{ip_address_id}",
        domain=warehouse,
    )

    # Project related Admin pages
    config.add_route("admin.project.list", "/admin/projects/", domain=warehouse)
    config.add_route(
        "admin.project.detail",
        "/admin/projects/{project_name}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.releases",
        "/admin/projects/{project_name}/releases/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.release",
        "/admin/projects/{project_name}/release/{version}",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/{version}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.release.render",
        "/admin/projects/{project_name}/release/{version}/render/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/{version}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.observations",
        "/admin/projects/{project_name}/observations/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.add_project_observation",
        "/admin/projects/{project_name}/add_project_observation/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.release.observations",
        "/admin/projects/{project_name}/release/{version}/observations/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/{version}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.release.add_release_observation",
        "/admin/projects/{project_name}/release/{version}/add_release_observation/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}/{version}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.remove_from_quarantine",
        "/admin/projects/{project_name}/remove_from_quarantine/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.journals",
        "/admin/projects/{project_name}/journals/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.set_upload_limit",
        "/admin/projects/{project_name}/set_upload_limit/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.set_total_size_limit",
        "/admin/projects/{project_name}/set_total_size_limit/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.add_role",
        "/admin/projects/{project_name}/add_role/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.delete_role",
        "/admin/projects/{project_name}/delete_role/{role_id}/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.delete",
        "/admin/projects/{project_name}/delete/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.reindex",
        "/admin/projects/{project_name}/reindex/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.archive",
        "/admin/projects/{project_name}/archive/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.project.unarchive",
        "/admin/projects/{project_name}/unarchive/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )

    # Journal related Admin pages
    config.add_route("admin.journals.list", "/admin/journals/", domain=warehouse)

    # Prohibited Project Name related Admin pages
    config.add_route(
        "admin.prohibited_project_names.list",
        "/admin/prohibited_project_names/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.add",
        "/admin/prohibited_project_names/add/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.bulk_add",
        "/admin/prohibited_project_names/bulk/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.remove",
        "/admin/prohibited_project_names/remove/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_project_names.release",
        "/admin/prohibited_project_names/release/",
        domain=warehouse,
    )
    # Prohibited Username related Admin pages
    config.add_route(
        "admin.prohibited_user_names.list",
        "/admin/prohibited_user_names/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_user_names.bulk_add",
        "/admin/prohibited_user_names/bulk/",
        domain=warehouse,
    )
    # Prohibited Email related Admin pages
    config.add_route(
        "admin.prohibited_email_domains.list",
        "/admin/prohibited_email_domains/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_email_domains.add",
        "/admin/prohibited_email_domains/add/",
        domain=warehouse,
    )
    config.add_route(
        "admin.prohibited_email_domains.remove",
        "/admin/prohibited_email_domains/remove/",
        domain=warehouse,
    )

    # Observation related Admin pages
    config.add_route(
        "admin.observations.list", "/admin/observations/", domain=warehouse
    )
    config.add_route("admin.quarantine.list", "/admin/quarantine/", domain=warehouse)
    config.add_route(
        "admin.malware_reports.list",
        "/admin/malware_reports/",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.project.list",
        "/admin/projects/{project_name}/malware_reports/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.project.verdict_not_malware",
        "/admin/projects/{project_name}/malware_reports/not_malware/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.project.verdict_quarantine",
        "/admin/projects/{project_name}/malware_reports/quarantine/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.project.verdict_remove_malware",
        "/admin/projects/{project_name}/malware_reports/remove_malware/",
        factory="warehouse.packaging.models:ProjectFactory",
        traverse="/{project_name}",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.detail",
        "/admin/malware_reports/{observation_id}/",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.detail.add_helpscout_conversation",
        "/admin/malware_reports/{observation_id}/add_helpscout_conversation/",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.detail.verdict_not_malware",
        "/admin/malware_reports/{observation_id}/not_malware/",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.detail.verdict_quarantine",
        "/admin/malware_reports/{observation_id}/quarantine/",
        domain=warehouse,
    )
    config.add_route(
        "admin.malware_reports.detail.verdict_remove_malware",
        "/admin/malware_reports/{observation_id}/remove_malware/",
        domain=warehouse,
    )

    # Email related Admin pages
    config.add_route("admin.emails.list", "/admin/emails/", domain=warehouse)
    config.add_route("admin.emails.mass", "/admin/emails/mass/", domain=warehouse)
    config.add_route(
        "admin.emails.detail", "/admin/emails/{email_id}/", domain=warehouse
    )

    # Flags
    config.add_route("admin.flags", "/admin/flags/", domain=warehouse)
    config.add_route("admin.flags.edit", "/admin/flags/edit/", domain=warehouse)

    # Sponsor related Admin pages
    config.add_route("admin.sponsor.list", "/admin/sponsors/", domain=warehouse)
    config.add_route(
        "admin.sponsor.create", "/admin/sponsors/create/", domain=warehouse
    )
    config.add_route(
        "admin.sponsor.delete", "/admin/sponsors/{sponsor_id}/delete/", domain=warehouse
    )
    config.add_route(
        "admin.sponsor.edit", "/admin/sponsors/{sponsor_id}/", domain=warehouse
    )

    # Banner related Admin pages
    config.add_route("admin.banner.list", "/admin/banners/", domain=warehouse)
    config.add_route("admin.banner.create", "/admin/banners/create/", domain=warehouse)
    config.add_route(
        "admin.banner.delete", "/admin/banners/{banner_id}/delete/", domain=warehouse
    )
    config.add_route(
        "admin.banner.preview", "/admin/banners/{banner_id}/preview/", domain=warehouse
    )
    config.add_route(
        "admin.banner.edit", "/admin/banners/{banner_id}/", domain=warehouse
    )

    # Helpscout Sidebar
    config.add_route("admin.helpscout", "/admin/helpscout/app/", domain=warehouse)
