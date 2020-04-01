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

import queue
import threading

import pretend

import warehouse.http

_REQUEST = pretend.stub(
    log=pretend.stub(debug=pretend.call_recorder(lambda *args: None))
)


class TestSession:
    def test_create(self):
        config = {"verify": "foo"}

        factory = warehouse.http.ThreadLocalSessionFactory(config)
        session_a, session_b = factory(_REQUEST), factory(_REQUEST)
        assert session_a is session_b
        assert session_a.verify == session_b.verify == config["verify"]

    def test_threads(self):
        def _test_factory(fifo, start):
            start.wait()
            factory = warehouse.http.ThreadLocalSessionFactory()
            # the actual session instance is stuck into the queue here as to
            # maintain a reference so it's not gc'd (which can result in id
            # reuse)
            fifo.put((threading.get_ident(), factory(_REQUEST)))

        start = threading.Event()

        fifo = queue.Queue()
        threads = [
            threading.Thread(target=_test_factory, args=(fifo, start))
            for _ in range(10)
        ]

        for thread in threads:
            thread.start()

        start.set()

        for thread in threads:
            thread.join()

        # data pushed into the queue is (threadid, session).
        # this basically proves that the session object id is different per
        # thread
        results = [fifo.get() for _ in range(len(threads))]
        idents, objects = zip(*results)
        assert len(set(idents)) == len(threads)
        assert len(set(id(obj) for obj in objects)) == len(threads)


def test_includeme():
    config = pretend.stub(
        registry=pretend.stub(settings={}),
        add_request_method=pretend.call_recorder(lambda *args, **kwargs: None),
    )
    warehouse.http.includeme(config)

    assert len(config.add_request_method.calls) == 1
    call = config.add_request_method.calls[0]
    assert isinstance(call.args[0], warehouse.http.ThreadLocalSessionFactory)
    assert call.kwargs == {"name": "http", "reify": True}
