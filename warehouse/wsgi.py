# SPDX-License-Identifier: Apache-2.0

from warehouse.config import configure

application = configure().make_wsgi_app()
