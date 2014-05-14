import collections
import copy
import operator

import charlatan
import pytest

from charlatan import _compat
from charlatan.depgraph import DepGraph
from charlatan.file_format import RelationshipToken, load_file
from charlatan.fixture_collection import (
    ListFixtureCollection, DictFixtureCollection
)


db_fixtures = pytest.mark.db_fixtures


class FixtureDict(collections.UserDict):

    def __init__(self, initial_data, table=None):
        super(FixtureDict, self).__init__(initial_data)

        self.table = table


class Fixture(charlatan.Fixture):

    def get_instance(self, path=None, include_relationships=True, fields=None):
        """
        Copied from charlatan, modifications are marked.
        """

        self.inherit_from_parent()  # Does the modification in place.

        if self.database_id:
            object_class = self.get_class()
            # No need to create a new object, just get it from the db
            instance = (
                self.fixture_manager.session.query(object_class)
                .get(self.database_id)
            )

        else:
            # We need to do a copy since we're modifying them.
            params = copy.deepcopy(self.fields)
            if fields:
                params.update(fields)

            # Get the class to instantiate
            object_class = self.get_class()

            # Does not return anything, does the modification in place (in
            # fields).
            self._process_relationships(params,
                                        remove=not include_relationships)

            # ### START MODIFICATION
            if object_class is not None:
                # This has been modified to store the table, instead of
                # creating an instance of the "model".
                instance = FixtureDict(params, table=object_class)
            else:
                # This has been modified to return our FixtureDict, with an
                # empty table attribute
                instance = FixtureDict(params)
            # ### END MODIFICATON

        # Do any extra assignment
        for attr, value in self.post_creation.items():
            if isinstance(value, RelationshipToken):
                value = self.get_relationship(value)

            setattr(instance, attr, value)

        if path:
            return operator.attrgetter(path)(instance)
        else:
            return instance


class FixturesManager(charlatan.FixturesManager):

    def __init__(self, engine):
        super(FixturesManager, self).__init__()
        self.engine = engine

    def _load_fixtures(self, filename):
        """
        Copied from Charlatan, no modifications were made, other than by
        redefining it here, it will use our Fixture class instead of the
        one that came with charlatan.
        """

        content = load_file(filename)

        fixtures = {}
        for k, v in _compat.iteritems(content):

            if "objects" in v:
                # It's a collection of fictures.
                fixtures[k] = self._handle_collection(
                    namespace=k,
                    definition=v,
                    objects=v["objects"],
                )

            # Named fixtures
            else:
                if "id" in v:
                    # Renaming id because it's a Python builtin function
                    v["id_"] = v["id"]
                    del v["id"]

                fixtures[k] = Fixture(key=k, fixture_manager=self, **v)

        d = DepGraph()
        for fixture in fixtures.values():
            for dependency, _ in fixture.extract_relationships():
                d.add_edge(dependency, fixture.key)

        # This does nothing except raise an error if there's a cycle
        d.topo_sort()
        return fixtures, d

    def _handle_collection(self, namespace, definition, objects):
        """
        Copied from Charlatan, no modifications were made, other than by
        redefining it here, it will use our Fixture class instead of the
        one that came with charlatan.
        """

        if isinstance(objects, list):
            klass = ListFixtureCollection
        else:
            klass = DictFixtureCollection

        collection = klass(
            key=namespace,
            fixture_manager=self,
            model=definition.get('model'),
            fields=definition.get('fields'),
            post_creation=definition.get('post_creation'),
            inherit_from=definition.get('inherit_from'),
            depend_on=definition.get('depend_on'),
        )

        for name, new_fields in collection.iterator(objects):
            qualified_name = "%s.%s" % (namespace, name)

            fixture = Fixture(
                key=qualified_name,
                fixture_manager=self,
                # Automatically inherit from the collection
                inherit_from=namespace,
                fields=new_fields,
                # The rest (model, default fields, etc.) is
                # automatically inherited from the collection.
            )
            collection.add(name, fixture)

        return collection

    def save_instance(self, instance):
        if isinstance(instance, FixtureDict):
            # We have one of our FixtureDict's, thus we should use our custom
            # save logic.
            if instance.table is not None:
                # We have a table, go ahead and save it.
                self.engine.execute(
                    instance.table.insert().values(**instance)
                )
        else:
            # This isn't a FixtureDict, so we should go ahead and let charlatan
            # do it's normal logic
            return super(FixturesManager, self).save_instance(instance)
