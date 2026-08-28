/* SPDX-License-Identifier: Apache-2.0 */

import { TabulatorFull as Tabulator } from "tabulator-tables";

// Build linked cells as DOM nodes so journal-supplied values are never
// interpreted as HTML. Columns without a formatter use Tabulator's default
// `plaintext` formatter, which entity-escapes values itself.
function linkCell(urlField) {
  return function (cell) {
    const value = cell.getValue();
    if (!value) {
      return "";
    }
    const url = cell.getRow().getData()[urlField];
    if (!url) {
      return document.createTextNode(value);
    }
    const link = document.createElement("a");
    link.href = url;
    link.textContent = value;
    return link;
  };
}

function dateCell(cell) {
  const value = cell.getValue();
  return value ? value.replace("T", " ").slice(0, 19) : "";
}

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

  // The latest response, kept for the footer counter. The server sends an
  // exact `total` when the final page is in reach and a `total_estimate`
  // when browsing unfiltered; both are null mid-way through a filtered
  // result, where counting is what made the old page time out.
  let lastResponse = null;

  new Tabulator(element, {
    layout: "fitColumns",
    placeholder: "No matching journal entries",
    pagination: true,
    paginationMode: "remote",
    paginationSize: 25,
    ajaxResponse: function (url, params, response) {
      lastResponse = response;
      return response;
    },
    paginationCounter: function (pageSize, currentRow) {
      if (!lastResponse?.data.length) {
        return; // the table placeholder already says there are no rows
      }
      const first = currentRow.toLocaleString();
      const last = (currentRow + lastResponse.data.length - 1).toLocaleString();
      const total = lastResponse.total ?? lastResponse.total_estimate;
      if (total == null) {
        return document.createTextNode(`Showing rows ${first}-${last}`);
      }
      const approx = lastResponse.total == null ? "~" : "";
      return document.createTextNode(
        `Showing ${first}-${last} of ${approx}${total.toLocaleString()} rows`,
      );
    },
    sortMode: "remote",
    filterMode: "remote",
    columnHeaderSortMulti: false,
    ajaxURL: element.dataset.url,
    initialSort: [{ column: "submitted_date", dir: "desc" }],
    initialHeaderFilter: initialHeaderFilter,
    columnDefaults: {
      headerFilter: "input",
      headerFilterLiveFilter: false,
    },
    columns: columns,
  });
}
