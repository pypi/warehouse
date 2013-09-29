from werkzeug.routing import Rule, EndpointPrefix, Submount

__urls__ = [
    EndpointPrefix("warehouse.legacy.simple.", [
        Submount("/simple", [
            Rule("/", methods=["GET"], endpoint="index"),
            Rule("/<project_name>/", methods=["GET"], endpoint="project"),
        ]),
        Rule("/packages/<path:path>", methods=["GET"], endpoint="package"),
    ]),
]
