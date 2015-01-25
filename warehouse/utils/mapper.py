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

import asyncio
import functools
import inspect

from aiopyramid.config import CoroutineOrExecutorMapper as _BaseMapper
from aiopyramid.helpers import is_generator


class CoroutineOrExecutorMapper(_BaseMapper):

    def run_in_executor_view(self, view):
        # aiopyramid normally would run a non coroutine view using
        # asyncio.get_event_loop().run_in_executor, however we don't want to
        # do that. We're going to assume that any function that does not
        # yield does not do any IO and just return the mapped view directly.
        return view


class WarehouseMapper(CoroutineOrExecutorMapper):

    def __call__(self, view):
        # Store the original view, because after we wrap it we need to know if
        # it should be wrapped with asyncio.coroutine or not.
        original = view

        # Wrap our view with our wrapper which will pull items out of the
        # matchdict and pass it into the given view.
        view = self._wrap_with_matchdict(view)

        # Determine if the original view was an asyncio coroutine or not, if it
        # was then we want to wrap our wrapped view with asyncio.coroutine so
        # that it'll act as a coroutine.
        if (
            asyncio.iscoroutinefunction(original) or
            is_generator(original) or
            is_generator(
                getattr(original, '__call__', None)
            )
        ):
            view = asyncio.coroutine(view)

        # Finally, call into the aiopyramid CoroutineOrExecutorMapper which
        # will call this view as either a coroutine or as a sync view.
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
