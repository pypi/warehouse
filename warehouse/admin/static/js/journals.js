/* SPDX-License-Identifier: Apache-2.0 */

import { dateCell, linkCell, remoteTable } from "./utils/remote_table";

const element = document.getElementById("journals-table");
if (element) {
  // Project-scoped pages pin the name filter via a data attribute: a page
  // headed "Journal Entries For <project>" must not show other projects'
  // entries.
  const pinnedName = element.dataset.filterName;

  const columns = [
    {
      title: "Name",
      field: "name",
      formatter: linkCell("project_link"),
      headerFilterPlaceholder: "exact name",
      // A pinned filter renders as a disabled input the user cannot edit.
      headerFilterParams: pinnedName
        ? { elementAttributes: { disabled: "disabled" } }
        : {},
    },
    {
      title: "Version",
      field: "version",
      headerFilterPlaceholder: "exact version",
      headerSort: false,
      width: 140,
    },
    {
      title: "Date",
      field: "submitted_date",
      formatter: dateCell,
      headerFilterPlaceholder: "on/before YYYY-MM-DD",
      width: 200,
    },
    {
      title: "Submitted By",
      field: "submitted_by",
      formatter: linkCell("submitted_by_link"),
      headerFilterPlaceholder: "username",
      width: 200,
    },
    {
      title: "Action",
      field: "action",
      headerFilterPlaceholder: "action prefix",
      headerSort: false,
    },
  ];

  // Allow deep-linking any filterable column, e.g.
  // /admin/journals/?submitted_by=someuser; the pin wins over a
  // query-param override.
  const query = new URLSearchParams(window.location.search);
  if (pinnedName) {
    query.set("name", pinnedName);
  }
  const initialHeaderFilter = columns
    .map((column) => column.field)
    .filter((field) => query.get(field))
    .map((field) => ({ field: field, value: query.get(field) }));

  remoteTable(element, {
    placeholder: "No matching journal entries",
    initialSort: [{ column: "submitted_date", dir: "desc" }],
    initialHeaderFilter: initialHeaderFilter,
    columnDefaults: {
      headerFilter: "input",
      headerFilterLiveFilter: false,
    },
    columns: columns,
  });
}
