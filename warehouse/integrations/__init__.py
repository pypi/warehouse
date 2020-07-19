def includeme(config):

    # Register the service for checking GitHub token scanning requests signatures.
    token_scanning_class = config.maybe_dotted(
        config.registry.settings.get(
            "github_token_scanning.backend", GitHubTokenScanningPayloadVerifyService
        )
    )
    config.register_service_factory(
        token_scanning_class.create_service, IGitHubTokenScanningPayloadVerifyService
    )

    config.add_route_predicate("headers", HeadersPredicate)

