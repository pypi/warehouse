def includeme(config):

    config.add_route_predicate("headers", HeadersPredicate)

