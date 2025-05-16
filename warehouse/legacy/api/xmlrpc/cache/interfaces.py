# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class CacheError(Exception):
    pass


class IXMLRPCCache(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def fetch(func, args, kwargs, key, tag, expire):
        """
        Gets cached function return value from the cache or calls func with the
        supplied args and kwargs, stashing it in the cache. Cache is drawn from
        by the specified func.__name__ and key. A tag is set on the cached
        response which can be used for purging. Set expire to override default
        expiration.
        """

    def purge(tag):
        """
        Issues a purge, clearing all cached objects associated with the tag
        from the cache.
        """

    def purge_tags(tags):
        """
        Issues a purge, clearing all cached objects associated with each tag
        in the iterable tags.
        """
