# SPDX-License-Identifier: Apache-2.0

import click

from trove_classifiers import all_classifiers as sorted_classifiers

from warehouse.cli import warehouse


@warehouse.group()
def classifiers():
    """
    Manage the Warehouse Malware Checks.
    """


@classifiers.command()
@click.pass_obj
def sync(config):
    """
    Sync the Warehouse database with the classifiers.
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.classifiers.models import Classifier
    from warehouse.db import Session

    session = Session(bind=config.registry["sqlalchemy.engine"])

    # Look up all of the valid classifiers
    all_classifiers = session.query(Classifier).all()

    # Determine if we need to add any new classifiers to the database
    missing_classifiers = set(sorted_classifiers) - {
        c.classifier for c in all_classifiers
    }

    # Add any new classifiers to the database
    if missing_classifiers:
        for name in missing_classifiers:
            missing_classifier = Classifier(
                classifier=name, ordering=sorted_classifiers.index(name)
            )
            session.add(missing_classifier)

    # Check to see if any of our existing classifiers need their ordering
    # changed
    for classifier in all_classifiers:
        classifier.ordering = sorted_classifiers.index(classifier.classifier)

    session.commit()
