/* SPDX-License-Identifier: Apache-2.0 */

import { dateCell, linkCell, remoteTable } from "./utils/remote_table";

const element = document.getElementById("observations-table");
if (element) {
  const table = remoteTable(element, {
    placeholder: "No matching observations",
    initialSort: [{ column: "created", dir: "desc" }],
    columns: [
      {
        title: "Created",
        field: "created",
        formatter: dateCell,
        width: 200,
      },
      {
        title: "Kind",
        field: "kind",
        // The row carries both the raw kind (which the filter sends back) and
        // its display label, so the column shows the label for the value.
        formatter: (cell) => document.createTextNode(cell.getData().kind_display),
        width: 200,
      },
      {
        title: "Related",
        field: "related",
        formatter: linkCell("related_link"),
        headerSort: false,
      },
      {
        title: "Summary",
        field: "summary",
        headerFilter: "input",
        headerFilterLiveFilter: false,
        headerFilterPlaceholder: "search summary or related",
        headerSort: false,
      },
      {
        title: "Observer",
        field: "observer",
        formatter: linkCell("observer_link"),
        headerSort: false,
        width: 200,
      },
    ],
  });

  // The kind dropdown drives the only programmatic filter, so setting it
  // replaces the previous selection and clearing it leaves the Summary
  // header filter untouched.
  const kindFilter = document.getElementById("observations-kind-filter");
  if (kindFilter) {
    kindFilter.addEventListener("change", function () {
      if (this.value) {
        table.setFilter("kind", "=", this.value);
      } else {
        table.clearFilter();
      }
    });
  }
}
