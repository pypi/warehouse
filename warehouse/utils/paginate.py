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

from paginate import Page


class _OpenSearchWrapper:
    max_results = 10000

    def __init__(self, query):
        self.query = query
        self.results = None
        self.best_guess = None

    def __getitem__(self, range):
        # If we're asking for a range that extends past our maximum results,
        # then we need to clamp the start of our slice to our maximum results
        # size, and make sure that the end of our slice >= to that to ensure a
        # consistent slice.
        if range.start > self.max_results:
            range = slice(
                self.max_results, max(range.stop, self.max_results), range.step
            )

        # If we're being asked for a range that extends past our maximum result
        # then we'll clamp it to the maximum result size and stop there.
        if range.stop > self.max_results:
            range = slice(range.start, self.max_results, range.step)

        if self.results is not None:
            raise RuntimeError("Cannot reslice after having already sliced.")
        self.results = self.query[range].execute()

        if hasattr(self.results, "suggest"):
            if self.results.suggest.name_suggestion:
                suggestion = self.results.suggest.name_suggestion[0]
                if suggestion.options:
                    self.best_guess = suggestion.options[0]

        return list(self.results)

    def __len__(self):
        if self.results is None:
            raise RuntimeError("Cannot get length until a slice.")
        if isinstance(self.results.hits.total, int):
            return min(self.results.hits.total, self.max_results)
        return min(self.results.hits.total["value"], self.max_results)


def OpenSearchPage(*args, **kwargs):  # noqa
    kwargs.setdefault("wrapper_class", _OpenSearchWrapper)
    return Page(*args, **kwargs)


def paginate_url_factory(request, query_arg="page"):
    def make_url(page):
        query_seq = [
            (k, v)
            for k, vs in request.GET.dict_of_lists().items()
            for v in vs
            if k != query_arg
        ]
        query_seq += [(query_arg, page)]
        return request.current_route_path(_query=query_seq)

    return make_url
