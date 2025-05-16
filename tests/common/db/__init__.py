# SPDX-License-Identifier: Apache-2.0

from sqlalchemy.orm import scoped_session

from warehouse.db import Session

Session = scoped_session(Session)
