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

from datadog import DogStatsd
from zope.interface import implementer

from warehouse.metrics.interfaces import IMetricsService


class _NullTimingDecoratorContextManager:
    def __call__(self, fn):
        return fn

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@implementer(IMetricsService)
class NullMetrics:
    @classmethod
    def create_service(cls, context, request):
        return cls()

    def gauge(self, metric, value, tags=None, sample_rate=1):
        pass

    def increment(self, metric, value=1, tags=None, sample_rate=1):
        pass

    def decrement(self, metric, value=1, tags=None, sample_rate=1):
        pass

    def histogram(self, metric, value, tags=None, sample_rate=1):
        pass

    def distribution(self, metric, value, tags=None, sample_rate=1):
        pass

    def timing(self, metric, value, tags=None, sample_rate=1):
        pass

    def timed(self, metric=None, tags=None, sample_rate=1, use_ms=None):
        return _NullTimingDecoratorContextManager()

    def set(self, metric, value, tags=None, sample_rate=1):
        pass

    def event(
        self,
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
        pass

    def service_check(
        self, check_name, status, tags=None, timestamp=None, hostname=None, message=None
    ):
        pass


@implementer(IMetricsService)
class DataDogMetrics:
    def __init__(self, datadog):
        self._datadog = datadog

    @classmethod
    def create_service(cls, context, request):
        return cls(
            DogStatsd(
                host=request.registry.settings.get("metrics.host", "127.0.0.1"),
                port=int(request.registry.settings.get("metrics.port", 8125)),
                namespace=request.registry.settings.get("metrics.namespace"),
                use_ms=True,
            )
        )

    def gauge(self, metric, value, tags=None, sample_rate=1):
        self._datadog.gauge(metric, value, tags=tags, sample_rate=sample_rate)

    def increment(self, metric, value=1, tags=None, sample_rate=1):
        self._datadog.increment(metric, value, tags=tags, sample_rate=sample_rate)

    def decrement(self, metric, value=1, tags=None, sample_rate=1):
        self._datadog.decrement(metric, value, tags=tags, sample_rate=sample_rate)

    def histogram(self, metric, value, tags=None, sample_rate=1):
        self._datadog.histogram(metric, value, tags=tags, sample_rate=sample_rate)

    def distribution(self, metric, value, tags=None, sample_rate=1):
        self._datadog.distribution(metric, value, tags=tags, sample_rate=sample_rate)

    def timing(self, metric, value, tags=None, sample_rate=1):
        self._datadog.timing(metric, value, tags=tags, sample_rate=sample_rate)

    def timed(self, metric=None, tags=None, sample_rate=1, use_ms=None):
        return self._datadog.timed(
            metric, tags=tags, sample_rate=sample_rate, use_ms=use_ms
        )

    def set(self, metric, value, tags=None, sample_rate=1):
        self._datadog.set(metric, value, tags=tags, sample_rate=sample_rate)

    def event(
        self,
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
        self._datadog.event(
            title,
            text,
            alert_type=alert_type,
            aggregation_key=aggregation_key,
            source_type_name=source_type_name,
            date_happened=date_happened,
            priority=priority,
            tags=tags,
            hostname=hostname,
        )

    def service_check(
        self, check_name, status, tags=None, timestamp=None, hostname=None, message=None
    ):
        self._datadog.service_check(
            check_name,
            status,
            tags=tags,
            timestamp=timestamp,
            hostname=hostname,
            message=message,
        )
