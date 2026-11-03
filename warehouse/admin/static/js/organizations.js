/* SPDX-License-Identifier: Apache-2.0 */

import { columnVisibilityMenu } from "./tabulator";
import { linkCell, remoteTable } from "./utils/remote_table";

const element = document.getElementById("organizations-table");
if (element) {
  // Cells are built as DOM nodes: every value here came from the server.
  const externalLinkCell = (cell) => {
    const link = document.createElement("a");
    link.href = cell.getValue();
    link.target = "_blank";
    link.rel = "nofollow noopener noreferrer";
    link.textContent = cell.getValue();
    return link;
  };

  const yesNoCell = (cell) => {
    const icon = document.createElement("i");
    icon.className = cell.getValue()
      ? "fa fa-fw fa-check text-green"
      : "fa fa-fw fa-times text-red";
    return icon;
  };

  // A chosen option sends its key; typing in the box would send its label,
  // so only the choice applies.
  const selectFilter = (values) => ({
    headerFilter: "list",
    headerFilterParams: { values: values },
    headerFilterLiveFilter: false,
  });

  const columns = [
    {
      title: "Account Name",
      field: "name",
      formatter: linkCell("detail_link"),
      headerFilter: "input",
      headerFilterPlaceholder: "contains",
      headerSort: true,
    },
    {
      title: "Organization",
      field: "display_name",
      headerFilter: "input",
      headerFilterPlaceholder: "contains",
    },
    {
      title: "URL",
      field: "link_url",
      formatter: externalLinkCell,
      headerFilter: "input",
      headerFilterPlaceholder: "contains",
    },
    {
      title: "Description",
      field: "description",
      headerFilter: "input",
      headerFilterPlaceholder: "contains",
    },
    {
      title: "Type",
      field: "orgtype",
      ...selectFilter({ "": "All", company: "Company", community: "Community" }),
      width: 130,
    },
    {
      title: "Status",
      field: "activity",
      ...selectFilter({
        "": "All",
        active: "Active",
        dormant: "Dormant",
        unused: "Unused",
        inactive: "Inactive",
      }),
      width: 130,
    },
    {
      title: "Subscription",
      // The filter asks for an active subscription, the cell shows whether
      // there is one.
      field: "subscription",
      formatter: (cell) =>
        yesNoCell({ getValue: () => cell.getData().active_subscription }),
      ...selectFilter({ "": "All", yes: "Has subscription" }),
      width: 150,
    },
    {
      title: "Good Standing",
      field: "good_standing",
      formatter: yesNoCell,
      width: 130,
    },
  ];

  // Allow deep-linking any filterable column, e.g.
  // /admin/organizations/?activity=inactive
  const query = new URLSearchParams(window.location.search);
  const initialHeaderFilter = columns
    .map((column) => column.field)
    .filter((field) => query.get(field))
    .map((field) => ({ field: field, value: query.get(field) }));

  remoteTable(element, {
    placeholder: "No matching organizations",
    initialSort: [{ column: "name", dir: "asc" }],
    initialHeaderFilter: initialHeaderFilter,
    columnDefaults: {
      headerSort: false,
      headerMenu: columnVisibilityMenu,
    },
    columns: columns,
  });
}
