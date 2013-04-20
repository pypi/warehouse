from unittest import mock

from warehouse.utils.templatetags.form_utils import renderfield


def test_renderfield():
    # Setup a mock field object
    field = mock.NonCallableMock()
    widget = mock.Mock(return_value="Rendered Widget!")
    field.as_widget = widget

    # Attempt to render the field
    rendered = renderfield(field, **{"class": "my-class"})

    # Verify results
    assert rendered == "Rendered Widget!"
    assert widget.call_count == 1
    assert widget.call_args == (tuple(), {"attrs": {"class": "my-class"}})
