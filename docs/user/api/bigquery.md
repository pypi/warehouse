# BigQuery Datasets

We use BigQuery to serve our public datasets. PyPI offers two tables whose
data is sourced from projects on PyPI. The tables and its pertaining data are licensed
under the [Creative Commons License].

## Download Statistics Table

*Table name*: `bigquery-public-data.pypi.file_downloads`

The download statistics table allows you learn more about downloads patterns of
packages hosted on PyPI.

This table is populated through the [Linehaul project] by streaming download
logs from PyPI to BigQuery. For more information on analyzing PyPI package
downloads, see the [Python Package Guide].

## Project Metadata Table

*Table name*: `bigquery-public-data.pypi.distribution_metadata`

We also have a table that provides access to distribution metadata
as outlined by the [core metadata specifications].

The table is meant to be a data dump of metadata from every
release on PyPI, which means that the rows in this BigQuery table
are immutable and are not removed even if a release or project is deleted.

[Creative Commons License]: https://creativecommons.org/licenses/by/4.0/
[Linehaul project]: https://github.com/pypa/linehaul-cloud-function/
[Python Package Guide]: https://packaging.python.org/guides/analyzing-pypi-package-downloads/
[core metadata specifications]: https://packaging.python.org/specifications/core-metadata/
