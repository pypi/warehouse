# SPDX-License-Identifier: Apache-2.0


class DevelopmentModeWarning(UserWarning):
    pass


class InsecureOIDCPublisherWarning(DevelopmentModeWarning):
    pass


class InsecureIntegrityServiceWarning(DevelopmentModeWarning):
    pass


class NullOAuthProviderServiceWarning(DevelopmentModeWarning):
    pass
