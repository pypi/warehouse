BigQuery Datasets
=================

We use BigQuery to serve our public datasets. PyPI offers two tables whose
data is sourced from projects on PyPI. The tables and its pertaining data are licensed
under the `Creative Commons License <https://creativecommons.org/licenses/by/4.0/>`_.

Download Statistics Table
-------------------------

The download statistics table allows you learn more about downloads patterns of
packages hosted on PyPI. This table is populated through the `Linehaul
project <https://github.com/pypa/linehaul>`_ by streaming download logs from PyPI
to BigQuery. For more information on analyzing PyPI package downloads, see the `Python
Package Guide <https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_

Project Metadata Table
----------------------

We also have a table that provides access to distribution metadata
as outlined by the `core metadata specifications <https://packaging.python.org/specifications/core-metadata/>`_.
The table is meant to be a data dump of metadata from every
release on PyPI, which means that the rows in this BigQuery table
are immutable and are not removed even if a release or project is deleted.
This data can be accessible under the ``the-psf.pypi.distribution_metadata``
public dataset on BigQuery.
