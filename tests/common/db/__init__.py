# SPDX-License-Identifier: Apache-2.0

from sqlalchemy.orm import scoped_session

from warehouse.db import Session as _Session

Session = scoped_session(_Session)
