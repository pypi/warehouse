# Tiltfile for Warehouse (PyPI) local development
# Infrastructure only - apps deployed via Cabotage

k8s_context('orbstack')

load('ext://namespace', 'namespace_create')
namespace_create('warehouse-dev')

# PostgreSQL - group namespace and PVC with deployment to avoid "unlabeled" section
k8s_yaml('k8s/dev/infra/postgres.yaml')
k8s_resource(
    'postgres',
    objects=[
        'warehouse-dev:namespace',
        'postgres-data:persistentvolumeclaim',
        'postgres-credentials:secret',
        'postgres-initdb:configmap',
    ],
    labels=['infra'],
)

# Redis - depends on postgres to sequence startup
k8s_yaml('k8s/dev/infra/redis.yaml')
k8s_resource(
    'redis',
    objects=[
        'redis-data:persistentvolumeclaim',
        'redis-credentials:secret',
    ],
    resource_deps=['postgres'],
    labels=['infra'],
)

# OpenSearch - search backend
k8s_yaml('k8s/dev/infra/opensearch.yaml')
k8s_resource(
    'opensearch',
    objects=[
        'opensearch-data:persistentvolumeclaim',
        'opensearch-credentials:secret',
    ],
    resource_deps=['postgres'],
    labels=['infra'],
)

# Maildev - email testing
k8s_yaml('k8s/dev/infra/maildev.yaml')
k8s_resource('maildev', labels=['infra'])

# Stripe mock - billing testing
k8s_yaml('k8s/dev/infra/stripe.yaml')
k8s_resource('stripe', labels=['infra'])

# Camo - image proxy (also hosts the ingress object to avoid unlabeled section)
k8s_yaml('k8s/dev/infra/camo.yaml')
k8s_yaml('k8s/dev/ingress.yaml')
k8s_resource(
    'camo',
    objects=['camo-credentials:secret', 'warehouse-ingress:ingress'],
    labels=['infra'],
)

# Bootstrap button in Tilt UI - creates org/project/apps in Cabotage
local_resource(
    'bootstrap-cabotage',
    cmd='cat scripts/bootstrap_cabotage.py | kubectl exec -i -n cabotage-dev deploy/cabotage-app -- sh -c "cd /opt/cabotage-app/src && python3"',
    labels=['setup'],
    auto_init=False,
    trigger_mode=TRIGGER_MODE_MANUAL,
)
