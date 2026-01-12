# SPDX-License-Identifier: Apache-2.0

import packaging.metadata
import pytest
from packaging.version import Version
from webob.multidict import MultiDict

from warehouse.forklift import metadata


def _assert_invalid_metadata(exc, field):
    invalids, other = exc.split(metadata.InvalidMetadata)

    assert other is None
    assert len(invalids.exceptions) == 1
    assert invalids.exceptions[0].field == field


class TestParse:
    def test_valid_from_file_24(self):
        meta = metadata.parse(
            b"Metadata-Version: 2.4\nName: foo\nVersion: 1.0\n"
            b"License-File: Something\nLicense-File: Something Else\n"
        )
        assert meta.name == "foo"
        assert meta.version == Version("1.0")
        assert meta.license_files == [
            "Something",
            "Something Else",
        ]

    def test_valid_from_file_25(self):
        meta = metadata.parse(
            b"Metadata-Version: 2.5\nName: foo\nVersion: 1.0\n"
            b"License-File: Something\nLicense-File: Something Else\n"
            b"Import-Name: widget\nImport-Namespace: gadget\n"
        )
        assert meta.name == "foo"
        assert meta.version == Version("1.0")
        assert meta.license_files == [
            "Something",
            "Something Else",
        ]
        assert meta.import_names == ["widget"]
        assert meta.import_namespaces == ["gadget"]

    def test_valid_from_form_24(self):
        data = MultiDict(metadata_version="2.4", name="spam", version="2.0")
        data.extend([("license_file", "Something"), ("license_file", "Something Else")])
        meta = metadata.parse(None, form_data=data)
        assert meta.name == "spam"
        assert meta.version == Version("2.0")
        assert meta.license_files == [
            "Something",
            "Something Else",
        ]

    def test_valid_from_form_25(self):
        data = MultiDict(metadata_version="2.5", name="spam", version="2.0")
        data.extend([("license_file", "Something"), ("license_file", "Something Else")])
        data.add("import_name", "widget")
        data.add("import_namespace", "gadget")
        meta = metadata.parse(None, form_data=data)
        assert meta.name == "spam"
        assert meta.version == Version("2.0")
        assert meta.license_files == [
            "Something",
            "Something Else",
        ]
        assert meta.import_names == ["widget"]
        assert meta.import_namespaces == ["gadget"]

    def test_invalid_no_data(self):
        with pytest.raises(metadata.NoMetadataError):
            metadata.parse(None)


class TestValidation:
    def test_invalid_metdata_version(self, monkeypatch):
        # Monkeypatch the packaging.metadata library to support a custom metadata
        # version that we know we'll never support.
        monkeypatch.setattr(
            packaging.metadata,
            "_VALID_METADATA_VERSIONS",
            packaging.metadata._VALID_METADATA_VERSIONS + ["100000.0"],
        )

        # Make sure that our monkeypatching worked
        meta = packaging.metadata.Metadata.from_raw(
            {"metadata_version": "100000.0"}, validate=False
        )
        assert meta.metadata_version == "100000.0"

        # We still should not support it
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(b"Metadata-Version: 100000.0\nName: foo\nVersion: 1.0\n")
        _assert_invalid_metadata(excinfo.value, "metadata-version")

    def test_version_cannot_contain_local(self):
        data = MultiDict(metadata_version="2.1", name="spam", version="2.0+local")
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, "version")

    @pytest.mark.parametrize(("field_name", "length"), metadata._LENGTH_LIMITS.items())
    def test_length_is_limited(self, field_name, length):
        # Correct
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "a" * (length - 1)},
        )
        meta = metadata.parse(None, form_data=data)
        assert getattr(meta, field_name) == "a" * (length - 1)

        # Too long
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "a" * (length + 1)},
        )
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, field_name)

    @pytest.mark.parametrize("field_name", ["author_email", "maintainer_email"])
    def test_valid_emails(self, field_name):
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "test@pypi.org"},
        )
        meta = metadata.parse(None, form_data=data)
        assert getattr(meta, field_name) == "test@pypi.org"

    @pytest.mark.parametrize("field_name", ["author_email", "maintainer_email"])
    def test_invalid_emails(self, field_name):
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "Foo <test>"},
        )
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, field_name.replace("_", "-"))

    @pytest.mark.parametrize("field_name", ["author_email", "maintainer_email"])
    def test_valid_emails_no_address(self, field_name):
        data = MultiDict(
            metadata_version="2.1", name="spam", version="2.0", **{field_name: "Foo <>"}
        )
        meta = metadata.parse(None, form_data=data)
        assert getattr(meta, field_name) == "Foo <>"

    def test_valid_classifier(self):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Classifier: Topic :: Utilities\n"
        )
        meta = metadata.parse(data)
        assert meta.classifiers == ["Topic :: Utilities"]

    def test_invalid_classifier(self):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Classifier: Something :: Or :: Other\n"
        )
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(data)
        _assert_invalid_metadata(excinfo.value, "classifier")

    @pytest.mark.parametrize("backfill", [True, False])
    def test_deprecated_classifiers_with_replacement(self, backfill):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Classifier: Natural Language :: Ukranian\n"
        )

        if not backfill:
            with pytest.raises(ExceptionGroup) as excinfo:
                metadata.parse(data)
            _assert_invalid_metadata(excinfo.value, "classifier")
        else:
            meta = metadata.parse(data, backfill=True)
            assert meta.classifiers == ["Natural Language :: Ukranian"]

    @pytest.mark.parametrize("backfill", [True, False])
    def test_deprecated_classifiers_no_replacement(self, backfill):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Classifier: Topic :: Communications :: Chat :: AOL Instant Messenger\n"
        )

        if not backfill:
            with pytest.raises(ExceptionGroup) as excinfo:
                metadata.parse(data)
            _assert_invalid_metadata(excinfo.value, "classifier")
        else:
            meta = metadata.parse(data, backfill=True)
            assert meta.classifiers == [
                "Topic :: Communications :: Chat :: AOL Instant Messenger"
            ]

    def test_valid_urls(self):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Home-page: https://example.com/\n"
        )
        meta = metadata.parse(data)
        assert meta.home_page == "https://example.com/"

    def test_invalid_urls(self):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Home-page: irc://example.com/\n"
        )
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(data)
        _assert_invalid_metadata(excinfo.value, "home-page")

    @pytest.mark.parametrize(
        "value",
        [
            ",",
            "",
            ", ".join(["a" * 100, "https://example.com/"]),
            "IRC,",
            "IRC, irc://example.com/",
        ],
    )
    def test_invalid_project_urls(self, value):
        data = b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\nProject-URL: "
        data += value.encode("utf8") + b"\n"
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(data)
        _assert_invalid_metadata(excinfo.value, "project-url")

    def test_valid_project_url(self):
        data = (
            b"Metadata-Version: 2.1\nName: spam\nVersion: 2.0\n"
            b"Project-URL: Foo, https://example.com/\n"
        )
        meta = metadata.parse(data)
        assert meta.project_urls == {"Foo": "https://example.com/"}

    @pytest.mark.parametrize(
        "field_name", ["provides_dist", "obsoletes_dist", "requires_dist"]
    )
    def test_valid_dists(self, field_name):
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "foo>=1.0"},
        )
        meta = metadata.parse(None, form_data=data)
        assert [str(r) for r in getattr(meta, field_name)] == ["foo>=1.0"]

    @pytest.mark.parametrize(
        "field_name", ["provides_dist", "obsoletes_dist", "requires_dist"]
    )
    def test_invalid_dists(self, field_name):
        if field_name != "requires_dist":
            # Invalid version
            data = MultiDict(
                metadata_version="2.1",
                name="spam",
                version="2.0",
                **{field_name: "foo >= dog"},
            )
            with pytest.raises(
                (
                    ExceptionGroup,
                    packaging.metadata.ExceptionGroup,
                    metadata.InvalidMetadata,
                )
            ) as excinfo:
                metadata.parse(None, form_data=data)
            _assert_invalid_metadata(excinfo.value, field_name.replace("_", "-"))

        # Invalid direct dependency
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            **{field_name: "foo @ https://example.com/foo-1.0.tar.gz"},
        )
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, field_name.replace("_", "-"))

    def test_valid_dynamic(self):
        data = MultiDict(metadata_version="2.2", name="spam", version="2.0")
        data.add("dynamic", "keywords")
        data.add("dynamic", "author")
        meta = metadata.parse(None, form_data=data)
        assert meta.dynamic == ["keywords", "author"]

    def test_invalid_dynamic(self):
        data = MultiDict(metadata_version="2.2", name="spam", version="2.0")
        data.add("dynamic", "Invalid")
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, "dynamic")

    def test_valid_dynamic_but_missing_from_our_enum(self, monkeypatch):
        """
        Handles the case where there are new metadata fields that pypa/packaging
        considers to be valid, but don't exist in our enum and would otherwise fail
        when inserting them into the database
        """
        monkeypatch.setattr(metadata, "DYNAMIC_FIELDS", [])
        data = MultiDict(metadata_version="2.2", name="spam", version="2.0")
        data.add("dynamic", "author")
        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse(None, form_data=data)
        _assert_invalid_metadata(excinfo.value, "dynamic")


class TestFromFormData:
    def test_valid(self):
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            keywords="foo, bar",
            unknown="lol",
        )
        data.add("project_urls", "Foo, https://example.com/")
        data.add("project_urls", "Bar, https://example.com/2/")

        meta = metadata.parse_form_metadata(data)
        assert meta.metadata_version == "2.1"
        assert meta.name == "spam"
        assert meta.version == Version("2.0")
        assert meta.keywords == ["foo", "bar"]
        assert meta.project_urls == {
            "Foo": "https://example.com/",
            "Bar": "https://example.com/2/",
        }

    def test_multiple_values_for_string_field(self):
        data = MultiDict(metadata_version="2.1", name="spam", version="2.0")
        data.add("summary", "one")
        data.add("summary", "two")

        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse_form_metadata(data)
        _assert_invalid_metadata(excinfo.value, "summary")

    def test_duplicate_labels_for_project_urls(self):
        data = MultiDict(metadata_version="2.1", name="spam", version="2.0")
        data.add("project_urls", "one, https://example.com/1/")
        data.add("project_urls", "one, https://example.com/2/")

        with pytest.raises(ExceptionGroup) as excinfo:
            metadata.parse_form_metadata(data)
        _assert_invalid_metadata(excinfo.value, "project_urls")

    def test_empty_strings_are_ignored(self):
        data = MultiDict(
            metadata_version="2.1",
            name="spam",
            version="2.0",
            description_content_type="",
        )

        meta = metadata.parse_form_metadata(data)
        assert meta.description_content_type is None


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Home-page", "homepage"),
        ("homepage", "homepage"),
        ("Home Page", "homepage"),
        ("HomePage", "homepage"),
        ("HOMEPAGE", "homepage"),
        ("What's New", "whatsnew"),
        ("Change_Log", "changelog"),
    ],
)
def test_normalize_project_url_label(label, expected):
    assert metadata.normalize_project_url_label(label) == expected
