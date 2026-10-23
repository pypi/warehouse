// SPDX-License-Identifier: Apache-2.0

// pypi.org/help/ redirects to the root of these docs, and the browser keeps
// the #anchor. Send links to the old help page's sections on to the page
// that now covers them. Anchors not listed here stay on the homepage.
(function () {
  if (window.location.pathname !== "/") {
    return;
  }

  const helpAnchors = {
    "packages": "/using-pypi/pypi-basics/#projects-releases-and-files-packages-on-pypi",
    "installing": "/using-pypi/finding-and-installing/#installing-packages",
    "publishing": "/publishing/publishing-to-pypi/#packaging-your-project",
    "trove-classifier": "/project_metadata/#classifiers",
    "yanked": "/using-pypi/pypi-basics/#yanked-release",
    "archived-project": "/using-pypi/pypi-basics/#archived-project",
    "pre-release-versioning": "/using-pypi/pypi-basics/#pre-release",
    "verified-email": "/your-account/managing-your-account/#email-address-verification",
    "compromised-password": "/your-account/security-alerts/#compromised-passwords",
    "suspicious-activity": "/your-account/security-alerts/#security-alerts-and-suspicious-activity",
    "compromised-token": "/your-account/security-alerts/#compromised-api-tokens",
    "twofa": "/your-account/two-factor-authentication/#what-is-two-factor-authentication",
    "two-factor-authentication": "/your-account/two-factor-authentication/#what-is-two-factor-authentication",
    "totp": "/your-account/two-factor-authentication/#authentication-application-totp",
    "utfkey": "/your-account/two-factor-authentication/#security-device-webauthn",
    "utfdevices": "/your-account/two-factor-authentication/#security-device-webauthn",
    "recoverycodes": "/your-account/two-factor-authentication/#recovery-codes",
    "recovery_code": "/your-account/two-factor-authentication/#recovery-codes",
    "apitoken": "/publishing/publishing-to-pypi/#using-an-api-token",
    "sensitiveactions": "/your-account/managing-your-account/#password-confirmation-for-sensitive-actions",
    "username-change": "/your-account/managing-your-account/#changing-your-pypi-username",
    "trusted-publishers": "/trusted-publishers/",
    "openid-connect": "/trusted-publishers/",
    "APIs": "/api/",
    "mirroring": "/about/service-availability/#private-indices-and-mirrors",
    "project-release-notifications": "/api/feeds/#project-releases-feed",
    "statistics": "/about/pypi-statistics/",
    "verify-hashes": "/using-pypi/package-security/package-integrity/#checksums",
    "private-indices": "/publishing/troubleshooting/#how-can-i-publish-my-private-packages-to-pypi",
    "project-name": "/project-management/choosing-a-name/#why-isnt-my-desired-project-name-available",
    "project-name-claim": "/project-management/choosing-a-name/#how-do-i-claim-an-abandoned-or-previously-registered-project-name",
    "collaborator-roles": "/project-management/managing-collaborators/#collaborator-roles",
    "request-ownership": "/project-management/managing-collaborators/#becoming-an-owner-or-maintainer",
    "description-content-type": "/project-management/project-descriptions/#specifying-the-long-description",
    "file-size-limit": "/project-management/storage-limits/#requesting-a-file-size-limit-increase",
    "project-size-limit": "/project-management/storage-limits/#requesting-a-project-size-limit-increase",
    "vulnerability-data": "/project-management/troubleshooting/#where-does-pypi-get-its-data-on-project-vulnerabilities-from-and-how-can-i-correct-it",
    "deletion": "/project-management/troubleshooting/#how-can-i-restore-a-deleted-project-release-or-file",
    "description-render-failure": "/publishing/troubleshooting/#why-am-i-getting-the-description-failed-to-render-error",
    "login-problem": "/your-account/account-recovery/#forgotten-password",
    "account-recovery": "/your-account/account-recovery/#lost-account-access",
    "invalid-auth": "/publishing/troubleshooting/#why-am-i-getting-an-invalid-or-non-existent-authentication-information-error-when-uploading-files",
    "tls-deprecation": "/using-pypi/troubleshooting/#why-am-i-getting-no-matching-distribution-found-or-could-not-fetch-url-errors-during-pip-install",
    "admin-intervention": "/about/security-and-internals/#temporarily-disabled-features",
    "file-name-reuse": "/publishing/troubleshooting/#why-am-i-getting-a-filename-or-contents-already-exists-or-filename-has-been-previously-used-error",
    "new-classifier": "/about/contributing/#requesting-a-new-trove-classifier",
    "feedback": "/about/contributing/#reporting-bugs",
    "totp_trouble": "/your-account/two-factor-authentication/#authentication-application-totp",
    "project_in_quarantine": "/project-management/troubleshooting/#my-project-or-release-says-its-in-quarantine-what-does-that-mean",
    "maintainers": "/about/who-maintains-pypi/",
    "sponsors": "/about/security-and-internals/#what-powers-pypi",
    "availability": "/about/service-availability/",
    "contributing": "/about/contributing/",
    "upcoming-changes": "/about/pypi-roadmap/",
    "ips": "/about/security-and-internals/#how-can-i-get-a-list-of-pypis-ip-addresses",
  };

  const target = helpAnchors[window.location.hash.slice(1)];
  if (target) {
    window.location.replace(target);
  }
})();
