# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import abc
import urllib.parse

from bok_choy.page_object import PageObject as _PageObject, unguarded
from bok_choy.promise import EmptyPromise


class PageObject(_PageObject):

    has_client_side_includes = True

    def __init__(self, *args, base_url, **kwargs):
        self.base_url = base_url
        super().__init__(*args, **kwargs)

    @property
    def url(self):
        return urllib.parse.urljoin(self.base_url, self.path)

    @property
    @abc.abstractmethod
    def path(self):
        """
        Return the path of the page.  This may be dynamic,
        determined by configuration options passed to the
        page object's constructor.
        """
        return None

    @unguarded
    def wait_for_page(self, timeout=30):
        b = self.browser

        # This is mostly copied from the original PageObject.wait_for_page(),
        # we duplicate it here because we want to check this before executing
        # our own checks.
        EmptyPromise(
            lambda: b.execute_script("return document.readyState=='complete'"),
            "The document and all sub-resources have finished loading.",
            timeout=timeout,
        ).fulfill()

        if self.has_client_side_includes:
            # Ensure that our HTML includes has successfully fired.
            EmptyPromise(
                lambda: b.execute_script(
                    "return window._WarehouseHTMLIncluded"),
                "The document has finished executing client side includes.",
                timeout=timeout,
            ).fulfill()

        # Run the rest of the items that we want to wait on the page for.
        return super().wait_for_page(timeout=timeout)
