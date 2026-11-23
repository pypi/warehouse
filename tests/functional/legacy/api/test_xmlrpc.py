# SPDX-License-Identifier: Apache-2.0

import xmlrpc.client

import pytest


def test_xmlrpc_raises_fault(webtest):
    with pytest.raises(xmlrpc.client.Fault):
        webtest.xmlrpc("/pypi", "list_packages", "one", "two")


def test_xmlrpc_nomethod(webtest):
    with pytest.raises(xmlrpc.client.Fault) as excinfo:
        webtest.xmlrpc("/pypi", "multipassssss")
    assert excinfo.value.faultCode == -32601
    assert excinfo.value.faultString == "server error; requested method not found"


def test_xmlrpc_succeeds(webtest):
    webtest.xmlrpc("/pypi", "changelog_last_serial")


def test_invalid_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; package_name: Missing required argument",
    ):
        webtest.xmlrpc("/pypi", "package_releases")


def test_excess_arguments(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; 1: Unexpected positional argument",
    ):
        webtest.xmlrpc("/pypi", "changelog_last_serial", 1)


def test_arguments_with_wrong_type(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; serial: Input should be a valid integer",
    ):
        webtest.xmlrpc("/pypi", "changelog_since_serial", "wrong!")


def test_serial_out_of_range(webtest):
    # xmlrpc.client refuses to marshal ints outside MININT/MAXINT, so post raw XML
    body = (
        "<?xml version='1.0'?><methodCall>"
        "<methodName>changelog_since_serial</methodName>"
        "<params><param><value><int>9000000000000</int></value></param></params>"
        "</methodCall>"
    )
    resp = webtest.post("/pypi", body, headers={"Content-Type": "text/xml"})
    with pytest.raises(
        xmlrpc.client.Fault,
        match=r"client error; serial: Input should be less than or equal to 2147483647",
    ):
        xmlrpc.client.loads(resp.body)


def test_multiple_garbage_types(webtest):
    with pytest.raises(
        xmlrpc.client.Fault,
        match=(
            r"client error; since: Input should be a valid integer; with_ids: "
            r"Input should be a valid boolean"
        ),
    ):
        webtest.xmlrpc("/pypi", "changelog", "wrong!", "also wrong!")
