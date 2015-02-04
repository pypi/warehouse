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

import functools
import inspect

from pyramid.config.views import DefaultViewMapper

from warehouse.sessions import InvalidSession


class WarehouseMapper(DefaultViewMapper):

    def __call__(self, view):
        # If this is one of our views, then we want to enable passing the
        # request.matchdict into the view function as kwargs.
        if view.__module__.startswith("warehouse."):
            # Wrap our view with our wrapper which will pull items out of the
            # matchdict and pass it into the given view.
            view = self._wrap_with_matchdict(view)

            # We want to wrap our view with a wrapper that will ensure that
            # only properly decorated views can access the session.
            view = self._wrap_with_session(view)

        # Call into the aiopyramid CoroutineOrExecutorMapper which will call
        # this view as either a coroutine or as a sync view.
        return super().__call__(view)

    def _wrap_with_matchdict(self, view):
        @functools.wraps(view)
        def wrapper(context, request):
            kwargs = request.matchdict.copy()

            if inspect.isclass(view):
                inst = view(request)
                meth = getattr(inst, self.attr)
                return meth(**kwargs)
            else:
                return view(request, **kwargs)

        return wrapper

    def _wrap_with_session(self, view):
        if not getattr(view, "_uses_session", None):
            @functools.wraps(view)
            def wrapper(context, request):
                # Store our original session so we can reapply it later.
                session = request.session

                # Replace our session with an InvalidSession() which will raise
                # an error for any attempt to use the session.
                request.session = InvalidSession()

                try:
                    # Actually call our view and get a respone object.
                    response = view(context, request)
                finally:
                    # Restore our session back to it's normal location so the
                    # Session response callback can function correctly.
                    request.session = session

                return response

            return wrapper

        return view
