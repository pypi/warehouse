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

from zope.interface import Interface


class IMetricsService(Interface):
    def gauge(metric, value, tags=None, sample_rate=1):
        """
        Record the value of a gauge, optionally setting a list of tags and a
        sample rate.
        """

    def increment(metric, value=1, tags=None, sample_rate=1):
        """
        Increment a counter, optionally setting a value, tags and a sample
        rate.
        """

    def decrement(metric, value=1, tags=None, sample_rate=1):
        """
        Decrement a counter, optionally setting a value, tags and a sample
        rate.
        """

    def histogram(metric, value, tags=None, sample_rate=1):
        """
        Sample a histogram value, optionally setting tags and a sample rate.
        """

    def distribution(metric, value, tags=None, sample_rate=1):
        """
        Send a global distribution value, optionally setting tags and a sample rate.
        """

    def timing(metric, value, tags=None, sample_rate=1):
        """
        Record a timing, optionally setting tags and a sample rate.
        """

    def timed(metric=None, tags=None, sample_rate=1, use_ms=None):
        """
        A decorator or context manager that will measure the distribution of a
        function's/context's run time. Optionally specify a list of tags or a
        sample rate. If the metric is not defined as a decorator, the module
        name and function name will be used. The metric is required as a context
        manager.

        ::
            @IMetricService.timed('user.query.time', sample_rate=0.5)
            def get_user(user_id):
                # Do what you need to ...
                pass
            # Is equivalent to ...
            with IMetricService.timed('user.query.time', sample_rate=0.5):
                # Do what you need to ...
                pass
            # Is equivalent to ...
            start = time.time()
            try:
                get_user(user_id)
            finally:
                IMetricService.timing('user.query.time', time.time() - start)
        """

    def set(metric, value, tags=None, sample_rate=1):
        """
        Sample a set value.
        """

    def event(
        title,
        text,
        alert_type=None,
        aggregation_key=None,
        source_type_name=None,
        date_happened=None,
        priority=None,
        tags=None,
        hostname=None,
    ):
        """
        Send an event.
        """

    def service_check(
        check_name, status, tags=None, timestamp=None, hostname=None, message=None
    ):
        """
        Send a service check run.
        """
