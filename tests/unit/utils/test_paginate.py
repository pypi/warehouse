# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from webob.multidict import MultiDict

from warehouse.utils import paginate


class FakeSuggestion:
    def __init__(self, options):
        self.options = options


class FakeSuggest:
    def __init__(self, name_suggestion):
        self.name_suggestion = name_suggestion


class FakeResult:
    def __init__(self, data, total):
        self.data = data
        self.total = total

    @property
    def hits(self):
        return types.SimpleNamespace(total={"value": self.total})

    def __iter__(self):
        yield from self.data


class FakeResult6:
    def __init__(self, data, total):
        self.data = data
        self.total = total

    @property
    def hits(self):
        return types.SimpleNamespace(total=self.total)

    def __iter__(self):
        yield from self.data


class FakeSuggestResult(FakeResult):
    def __init__(self, data, total, options=None, suggestion=None):
        super().__init__(data, total)
        self.options = options
        self.suggestion = suggestion

    @property
    def suggest(self):
        if self.suggestion is None:
            suggestion = FakeSuggestion(options=self.options)
            return FakeSuggest(name_suggestion=[suggestion])
        return FakeSuggest(name_suggestion=self.suggestion)


class FakeQuery:
    def __init__(self, fake):
        self.fake = fake
        self.range = slice(None)

    def __getitem__(self, range):
        self.range = range
        return self

    def execute(self):
        return FakeResult(self.fake[self.range], len(self.fake))


class FakeQuery6:
    def __init__(self, fake):
        self.fake = fake
        self.range = slice(None)

    def __getitem__(self, range):
        self.range = range
        return self

    def execute(self):
        return FakeResult6(self.fake[self.range], len(self.fake))


class FakeSuggestQuery(FakeQuery):
    def __init__(self, fake, options=None, suggestion=None):
        super().__init__(fake)
        self.options = options
        self.suggestion = suggestion

    def execute(self):
        data = self.fake[self.range]
        total = len(self.fake)
        return FakeSuggestResult(data, total, self.options, self.suggestion)


class TestOpenSearchWrapper:
    def test_slices_and_length(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        assert wrapper[1:3] == [2, 3]
        assert len(wrapper) == 6

    def test_slice_start_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[6:10] == []
        assert len(wrapper) == 5

    def test_slice_end_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[1:10] == [2, 3, 4, 5]
        assert len(wrapper) == 5

    def test_second_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper[1:3]

        with pytest.raises(RuntimeError):
            wrapper[1:3]

    def test_len_before_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))

        with pytest.raises(RuntimeError):
            len(wrapper)

    def test_best_guess_suggestion(self, mocker):
        fake_option = mocker.sentinel.fake_option
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[fake_option])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess == fake_option

    def test_best_guess_suggestion_no_suggestions(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], suggestion=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None

    def test_best_guess_suggestion_no_options(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None


class TestOpenSearchWrapper6:
    def test_slices_and_length(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        assert wrapper[1:3] == [2, 3]
        assert len(wrapper) == 6

    def test_slice_start_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[6:10] == []
        assert len(wrapper) == 5

    def test_slice_end_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[1:10] == [2, 3, 4, 5]
        assert len(wrapper) == 5

    def test_second_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper[1:3]

        with pytest.raises(RuntimeError):
            wrapper[1:3]

    def test_len_before_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))

        with pytest.raises(RuntimeError):
            len(wrapper)

    def test_best_guess_suggestion(self, mocker):
        fake_option = mocker.sentinel.fake_option
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[fake_option])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess == fake_option

    def test_best_guess_suggestion_no_suggestions(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], suggestion=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None

    def test_best_guess_suggestion_no_options(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None


def test_opensearch_page_has_wrapper(mocker):
    page_obj = mocker.sentinel.page_obj
    page_cls = mocker.patch.object(paginate, "Page", return_value=page_obj)

    assert paginate.OpenSearchPage("first", second="foo") is page_obj
    page_cls.assert_called_once_with(
        "first", second="foo", wrapper_class=paginate._OpenSearchWrapper
    )


def test_paginate_url(pyramid_request, mocker):
    pyramid_request.GET = MultiDict(pyramid_request.GET)
    pyramid_request.GET["foo"] = "bar"

    url = mocker.sentinel.url
    current_route_path = mocker.patch.object(
        pyramid_request, "current_route_path", autospec=True, return_value=url
    )

    url_maker = paginate.paginate_url_factory(pyramid_request)

    assert url_maker(5) is url
    current_route_path.assert_called_once_with(_query=[("foo", "bar"), ("page", 5)])
