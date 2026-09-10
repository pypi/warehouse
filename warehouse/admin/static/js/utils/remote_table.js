/* SPDX-License-Identifier: Apache-2.0 */

import { TabulatorFull as Tabulator } from "tabulator-tables";

/**
 * Shared pieces of the admin's JSON-fed Tabulator tables.
 *
 * Tables rendered server-side into a <table> instead opt in declaratively with
 * `data-tabulator` and need none of this; these helpers exist for the tables
 * whose rows arrive as JSON, where cell contents are data rather than markup.
 */

/**
 * Build a formatter rendering the cell as a link to `urlField`'s value.
 *
 * Cells are built as DOM nodes so server-supplied values are never interpreted
 * as HTML. Columns without a formatter use Tabulator's default `plaintext`
 * formatter, which entity-escapes values itself.
 */
export function linkCell(urlField) {
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

/** Render an ISO timestamp as `YYYY-MM-DD HH:MM:SS`. */
export function dateCell(cell) {
  const value = cell.getValue();
  return value ? value.replace("T", " ").slice(0, 19) : "";
}

/**
 * The message an endpoint sent with a 4xx, or null if there is not one.
 *
 * These endpoints reject a filter they cannot serve with a sentence saying
 * what to do about it — a date it cannot parse, a query that outran its timeout.
 * Pyramid pads its JSON error body with the generic status text, so the
 * view's own sentence is the last non-empty line of `message`.
 */
export async function loadErrorMessage(error) {
  if (!error || typeof error.json !== "function") {
    return null;
  }
  try {
    const body = await error.json();
    const lines = String(body.message || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    return lines.length ? lines[lines.length - 1] : null;
  } catch {
    return null;
  }
}

/**
 * Build a table whose rows come from one of the admin's Tabulator JSON
 * endpoints, reading its URL from the mount point's `data-url`.
 *
 * Sorting, filtering and paging all run server-side, so the table asks for one
 * page at a time and never holds the whole result set. Pass `overrides` for
 * the per-table pieces — at minimum `columns`, `placeholder` and `initialSort`.
 */
export function remoteTable(element, overrides) {
  const table = new Tabulator(element, {
    layout: "fitColumns",
    pagination: true,
    paginationMode: "remote",
    paginationSize: 25,
    sortMode: "remote",
    filterMode: "remote",
    // Remote sorting serves one ORDER BY, so offering multi-column sort in the
    // header would promise an ordering the endpoint will not honor.
    columnHeaderSortMulti: false,
    ajaxURL: element.dataset.url,
    // Long enough to read the message below. Clearing it sooner leaves the
    // previous query's rows on screen as though the new one had applied.
    dataLoaderErrorTimeout: 15000,
    ...overrides,
    // Last, and deliberately: `ajaxResponse` and `paginationCounter` are two
    // halves of one closure, and an override supplying only the first would
    // leave the counter reading a response it never saw.
    ...remotePaginationCounter(),
  });

  // Tabulator applies a response only if it is still the newest request, but
  // alerts on a failure whenever one arrives. Without the same check, a slow
  // query failing after a narrower one has already rendered paints an error
  // over valid rows and holds it there for `dataLoaderErrorTimeout`, so a
  // failure that a later load has already answered is cleared instead.
  let started = 0;
  let settled = 0;
  table.on("dataLoading", () => {
    started += 1;
  });
  table.on("dataLoaded", () => {
    settled = started;
  });

  table.on("dataLoadError", async (error) => {
    const request = started;
    const message = await loadErrorMessage(error);
    if (settled >= request) {
      table.clearAlert();
      return;
    }
    settled = request;
    if (message) {
      // Built as a node: Tabulator assigns anything else with `innerHTML`,
      // and this sentence comes from the server.
      const content = document.createElement("div");
      content.textContent = message;
      table.alert(content, "error");
    }
  });

  return table;
}

function remotePaginationCounter() {
  let lastResponse = null;

  return {
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
  };
}
