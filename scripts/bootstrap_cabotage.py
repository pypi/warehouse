#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Bootstrap Warehouse (PyPI) project in Cabotage.

This script creates the organization, project, and applications in Cabotage
with pre-configured environment variables for local development.

Run via:
    make tilt-bootstrap

Or manually:
    cat scripts/bootstrap_cabotage.py | kubectl exec -i -n cabotage-dev \
        deploy/cabotage-app -- sh -c "cd /opt/cabotage-app/src && python3"
"""

# This runs inside the Cabotage container
from cabotage.server import create_app, db
from cabotage.server.models import Organization, User
from cabotage.server.models.projects import Application, Configuration, Project

# Helper to avoid Tilt secret redaction (splits "warehouse" and "localdev123")
WH = "ware" + "house"
WH_DEV = WH + "-dev"
WH_SVC = WH_DEV + ".svc.cluster.local"
WH_ORB = WH_DEV + ".orb.local"
DB_PASS = "local" + "dev123"

# Configuration for Warehouse (PyPI)
WAREHOUSE_CONFIG = {
    "org": {
        "name": "Warehouse",
        "slug": WH,
    },
    "project": {
        "name": "Warehouse Dev",
        "slug": WH_DEV,
    },
    "apps": {
        "web": {
            "name": "Web",
            "slug": "web",
            "auto_deploy_branch": "main",
            "health_check_path": "/_health/",
            "deployment_timeout": 300,
            "process_counts": {"web": 1},
            "process_pod_classes": {"web": "m1.large"},
            "env": {
                # Core settings
                "ENCODING": "C.UTF-8",
                "WAREHOUSE_ENV": "development",
                "WAREHOUSE_TOKEN": "insecuretoken",
                "WAREHOUSE_IP_SALT": "insecure himalayan pink salt",
                # Database
                "DATABASE_URL": (
                    f"postgresql+psycopg://pypi:{DB_PASS}@postgres.{WH_SVC}/pypi"
                ),
                # OpenSearch
                "OPENSEARCH_URL": f"http://opensearch.{WH_SVC}:9200/development",
                # Redis
                "REDIS_URL": f"redis://redis.{WH_SVC}:6379",
                # URLs
                "USERDOCS_DOMAIN": "http://localhost:10000",
                "DOCS_URL": "https://pythonhosted.org/{project}/",
                "WAREHOUSE_LEGACY_DOMAIN": "pypi.python.org",
                "WAREHOUSE_ALLOWED_DOMAINS": f"127.0.0.1,localhost,{WH_ORB}",
                # Billing - stripe mock
                "BILLING_BACKEND": (
                    f"{WH}.subscriptions.services.MockStripeBillingService "
                    f"api_base=http://stripe.{WH_SVC}:12111 "
                    f"api_version=2020-08-27 domain={WH_ORB}"
                ),
                # Camo
                "CAMO_URL": f"http://camo.{WH_ORB}/",
                "CAMO_KEY": "insecurecamokey",
                # File storage backends
                "FILES_BACKEND": (
                    f"{WH}.packaging.services.LocalFileStorage "
                    f"path=/var/opt/warehouse/packages/ "
                    f"url=http://files.{WH_ORB}/packages/{{path}}"
                ),
                "ARCHIVE_FILES_BACKEND": (
                    f"{WH}.packaging.services.LocalArchiveFileStorage "
                    f"path=/var/opt/warehouse/packages-archive/ "
                    f"url=http://files.{WH_ORB}/packages-archive/{{path}}"
                ),
                "SIMPLE_BACKEND": (
                    f"{WH}.packaging.services.LocalSimpleStorage "
                    f"path=/var/opt/warehouse/simple/ "
                    f"url=http://files.{WH_ORB}/simple/{{path}}"
                ),
                "DOCS_BACKEND": (
                    f"{WH}.packaging.services.LocalDocsStorage "
                    f"path=/var/opt/warehouse/docs/"
                ),
                "SPONSORLOGOS_BACKEND": (
                    f"{WH}.admin.services.LocalSponsorLogoStorage "
                    f"path=/var/opt/warehouse/sponsorlogos/"
                ),
                # Cache
                "ORIGIN_CACHE": (
                    f"{WH}.cache.origin.fastly.NullFastlyCache "
                    f"api_key=some_api_key service_id=some_service_id"
                ),
                # Mail
                "MAIL_BACKEND": (
                    f"{WH}.email.services.ConsoleAndSMTPEmailSender "
                    f"host=maildev.{WH_SVC} port=1025 ssl=false "
                    f"sender=noreply@pypi.org"
                ),
                # Service backends
                "BREACHED_EMAILS": f"{WH}.accounts.NullEmailBreachedService",
                "BREACHED_PASSWORDS": f"{WH}.accounts.NullPasswordBreachedService",
                "OIDC_BACKEND": f"{WH}.oidc.services.NullOIDCPublisherService",
                "INTEGRITY_BACKEND": f"{WH}.attestations.services.NullIntegrityService",
                "GITHUB_OAUTH_BACKEND": f"{WH}.accounts.oauth.NullOAuthClient",
                "METRICS_BACKEND": f"{WH}.metrics.DataDogMetrics host=notdatadog",
                # Feature flags
                "TWOFACTORREQUIREMENT_ENABLED": "true",
                "TWOFACTORMANDATE_AVAILABLE": "true",
                "TWOFACTORMANDATE_ENABLED": "true",
                "OIDC_AUDIENCE": "pypi",
                "TERMS_NOTIFICATION_BATCH_SIZE": "0",
                # Captcha - test keys
                "RECAPTCHA_SITE_KEY": "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
                "CAPTCHA_BACKEND": f"{WH}.captcha.hcaptcha.Service",
                "HCAPTCHA_SITE_KEY": "10000000-ffff-ffff-ffff-000000000001",
                # Helpdesk
                "HELPDESK_BACKEND": f"{WH}.helpdesk.services.ConsoleHelpDeskService",
                "HELPDESK_NOTIFICATION_BACKEND": (
                    f"{WH}.helpdesk.services.ConsoleAdminNotificationService"
                ),
                # Status page
                "STATUSPAGE_URL": "https://2p66nmmycsj3.statuspage.io",
                # GitHub token scanning
                "GITHUB_TOKEN_SCANNING_META_API_URL": (
                    "http://notgithub:8000/meta/public_keys/token_scanning"
                ),
            },
            "secrets": {
                "SESSION_SECRET": "an insecure development secret",
                "TOKEN_PASSWORD_SECRET": "an insecure password reset secret key",
                "TOKEN_EMAIL_SECRET": "an insecure email verification secret key",
                "TOKEN_TWO_FACTOR_SECRET": "an insecure two-factor auth secret key",
                "TOKEN_REMEMBER_DEVICE_SECRET": (
                    "an insecure remember device auth secret key"
                ),
                "TOKEN_CONFIRM_LOGIN_SECRET": (
                    "an insecure confirm login auth secret key"
                ),
                "RECAPTCHA_SECRET_KEY": "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe",
                "HCAPTCHA_SECRET_KEY": "0x0000000000000000000000000000000000000000",
                "HIBP_API_KEY": "something-not-real",
                "AWS_ACCESS_KEY_ID": "foo",
                "AWS_SECRET_ACCESS_KEY": "foo",
            },
        },
        "worker": {
            "name": "Worker",
            "slug": "worker",
            "auto_deploy_branch": "main",
            "health_check_path": "/_health/",  # Required, even for workers
            "deployment_timeout": 300,
            "process_counts": {"worker": 1},
            "process_pod_classes": {"worker": "m1.medium"},
            "env": {
                # Same core settings as web
                "ENCODING": "C.UTF-8",
                "WAREHOUSE_ENV": "development",
                "WAREHOUSE_TOKEN": "insecuretoken",
                "WAREHOUSE_IP_SALT": "insecure himalayan pink salt",
                "C_FORCE_ROOT": "1",  # Celery root permission
                # Database
                "DATABASE_URL": (
                    f"postgresql+psycopg://pypi:{DB_PASS}@postgres.{WH_SVC}/pypi"
                ),
                # Redis
                "REDIS_URL": f"redis://redis.{WH_SVC}:6379",
                # File backends for worker
                "FILES_BACKEND": (
                    f"{WH}.packaging.services.LocalFileStorage "
                    f"path=/var/opt/warehouse/packages/ "
                    f"url=http://files.{WH_ORB}/packages/{{path}}"
                ),
                "ARCHIVE_FILES_BACKEND": (
                    f"{WH}.packaging.services.LocalArchiveFileStorage "
                    f"path=/var/opt/warehouse/packages-archive/ "
                    f"url=http://files.{WH_ORB}/packages-archive/{{path}}"
                ),
                "SIMPLE_BACKEND": (
                    f"{WH}.packaging.services.LocalSimpleStorage "
                    f"path=/var/opt/warehouse/simple/ "
                    f"url=http://files.{WH_ORB}/simple/{{path}}"
                ),
                # Mail
                "MAIL_BACKEND": (
                    f"{WH}.email.services.ConsoleAndSMTPEmailSender "
                    f"host=maildev.{WH_SVC} port=1025 ssl=false "
                    f"sender=noreply@pypi.org"
                ),
                # Service backends
                "BREACHED_EMAILS": f"{WH}.accounts.NullEmailBreachedService",
                "BREACHED_PASSWORDS": f"{WH}.accounts.NullPasswordBreachedService",
            },
            "secrets": {
                "SESSION_SECRET": "an insecure development secret",
                "AWS_ACCESS_KEY_ID": "foo",
                "AWS_SECRET_ACCESS_KEY": "foo",
            },
        },
        "files": {
            "name": "Files",
            "slug": "files",
            "auto_deploy_branch": "main",
            "health_check_path": "/",
            "deployment_timeout": 120,
            "process_counts": {"web": 1},
            "process_pod_classes": {"web": "m1.small"},
            "env": {
                # Simple static file server
                "PYTHONUNBUFFERED": "1",
            },
            "secrets": {},
        },
    },
}


def main():
    app = create_app()

    with app.app_context():
        # Check if org exists
        org = Organization.query.filter_by(
            slug=WAREHOUSE_CONFIG["org"]["slug"]
        ).first()

        if org:
            print(f"Organization '{org.slug}' exists. Updating apps...")
        else:
            # Get admin user (created by create_admin script)
            admin_user = User.query.filter_by(username="admin").first()
            if not admin_user:
                print("ERROR: Admin user not found. Run create_admin first.")
                return

            # Create organization
            org = Organization(
                name=WAREHOUSE_CONFIG["org"]["name"],
                slug=WAREHOUSE_CONFIG["org"]["slug"],
            )
            org.add_user(admin_user, admin=True)
            db.session.add(org)
            db.session.flush()
            print(f"Created organization: {org.name} ({org.slug})")

        # Get or create project
        proj = Project.query.filter_by(
            organization_id=org.id,
            slug=WAREHOUSE_CONFIG["project"]["slug"]
        ).first()

        if proj:
            print(f"Project '{proj.slug}' exists.")
        else:
            proj = Project(
                organization_id=org.id,
                name=WAREHOUSE_CONFIG["project"]["name"],
                slug=WAREHOUSE_CONFIG["project"]["slug"],
            )
            db.session.add(proj)
            db.session.flush()
            print(f"Created project: {proj.name} ({proj.slug})")

        # Create or update applications
        for app_slug, app_config in WAREHOUSE_CONFIG["apps"].items():
            application = Application.query.filter_by(
                project_id=proj.id,
                slug=app_config["slug"]
            ).first()

            if application:
                # Update existing app
                application.auto_deploy_branch = app_config.get(
                    "auto_deploy_branch", "main"
                )
                application.health_check_path = app_config.get(
                    "health_check_path", "/_health/"
                )
                application.deployment_timeout = app_config.get(
                    "deployment_timeout", 180
                )
                application.process_counts = app_config.get(
                    "process_counts", {"web": 1}
                )
                application.process_pod_classes = app_config.get(
                    "process_pod_classes", {"web": "m1.small"}
                )
                print(
                    f"  Updated application: {application.name} ({application.slug})"
                )
            else:
                # Create new app
                application = Application(
                    project_id=proj.id,
                    name=app_config["name"],
                    slug=app_config["slug"],
                    auto_deploy_branch=app_config.get(
                        "auto_deploy_branch", "main"
                    ),
                    health_check_path=app_config.get(
                        "health_check_path", "/_health/"
                    ),
                    deployment_timeout=app_config.get("deployment_timeout", 180),
                    process_counts=app_config.get("process_counts", {"web": 1}),
                    process_pod_classes=app_config.get(
                        "process_pod_classes", {"web": "m1.small"}
                    ),
                )
                db.session.add(application)
                db.session.flush()
                print(
                    f"  Created application: {application.name} ({application.slug})"
                )

            # Upsert environment variables
            for key, value in app_config.get("env", {}).items():
                config = Configuration.query.filter_by(
                    application_id=application.id,
                    name=key
                ).first()
                if config:
                    config.value = value
                    config.secret = False
                else:
                    config = Configuration(
                        application_id=application.id,
                        name=key,
                        value=value,
                        secret=False,
                    )
                    db.session.add(config)

            # Upsert secrets
            for key, value in app_config.get("secrets", {}).items():
                config = Configuration.query.filter_by(
                    application_id=application.id,
                    name=key
                ).first()
                if config:
                    config.value = value
                    config.secret = True
                else:
                    config = Configuration(
                        application_id=application.id,
                        name=key,
                        value=value,
                        secret=True,
                    )
                    db.session.add(config)

            env_count = len(app_config.get("env", {}))
            secrets_count = len(app_config.get("secrets", {}))
            print(f"    Synced {env_count} env vars, {secrets_count} secrets")

        db.session.commit()
        print("\nBootstrap complete!")
        # Split string to avoid Tilt secret redaction
        print(f"Visit: http://cabotage.192-168-139-2.nip.io/organizations/{WH}")


if __name__ == "__main__":
    main()
