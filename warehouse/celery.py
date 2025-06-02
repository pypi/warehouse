# SPDX-License-Identifier: Apache-2.0

from warehouse.config import configure

app = configure().make_celery_app()
