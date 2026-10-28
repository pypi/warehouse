/* SPDX-License-Identifier: Apache-2.0 */

import { dateCell, linkCell, remoteTable } from "./utils/remote_table";

const element = document.getElementById("users-table");
if (element) {
  // Cells are built as DOM nodes: every value here came from the server.
  const avatarCell = (cell) => {
    const image = document.createElement("img");
    image.src = cell.getValue();
    image.className = "img-circle";
    image.alt = "";
    return image;
  };

  const checkCell = (colour) => (cell) => {
    if (!cell.getValue()) {
      return "";
    }
    const icon = document.createElement("i");
    icon.className = `fa fa-check ${colour}`;
    return icon;
  };

  // A chosen option sends its key; typing in the box would send its label,
  // so only the choice applies.
  const selectFilter = (values) => ({
    headerFilter: "list",
    headerFilterParams: { values: values },
    headerFilterLiveFilter: false,
  });
  const yesNo = { "": "All", true: "Yes", false: "No" };

  const columns = [
    {
      title: "Image",
      field: "avatar_url",
      formatter: avatarCell,
      headerFilter: false,
      width: 60,
    },
    {
      title: "Username",
      field: "username",
      formatter: linkCell("detail_link"),
      headerFilter: "input",
      headerFilterPlaceholder: "contains",
      headerSort: true,
    },
    {
      title: "Name",
      field: "name",
    },
    {
      title: "Email",
      field: "email",
      headerFilter: "input",
      headerFilterPlaceholder: "contains, any address",
    },
    {
      title: "PyPI Roles",
      // The filter asks for any role, the cell shows which ones.
      field: "role",
      formatter: (cell) => document.createTextNode(cell.getData().roles),
      ...selectFilter({ "": "All", any: "Any role" }),
    },
    {
      title: "Active",
      field: "is_active",
      formatter: checkCell("text-green"),
      ...selectFilter(yesNo),
      width: 110,
    },
    {
      title: "2FA",
      field: "has_two_factor",
      formatter: checkCell("text-green"),
      width: 70,
    },
    {
      title: "Frozen",
      field: "is_frozen",
      formatter: checkCell("text-red"),
      ...selectFilter(yesNo),
      width: 110,
    },
    {
      title: "Joined",
      field: "date_joined",
      formatter: dateCell,
      width: 200,
    },
  ];

  // Allow deep-linking any filterable column, e.g.
  // /admin/users/?email=%40example.com
  const query = new URLSearchParams(window.location.search);
  const initialHeaderFilter = columns
    .map((column) => column.field)
    .filter((field) => query.get(field))
    .map((field) => ({ field: field, value: query.get(field) }));

  remoteTable(element, {
    placeholder: "No matching users",
    initialSort: [{ column: "username", dir: "asc" }],
    initialHeaderFilter: initialHeaderFilter,
    columnDefaults: {
      headerSort: false,
    },
    columns: columns,
  });
}
