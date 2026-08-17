/* SPDX-License-Identifier: Apache-2.0 */

import { TabulatorFull as Tabulator } from "tabulator-tables";

import filesize from "./utils/filesize";

// Cells hold raw byte counts so `tabulator-sorter="number"` orders them
// correctly, while the column still displays a human-readable size.
Tabulator.extendModule("format", "formatters", {
  filesize: (cell) => filesize(cell.getValue()),
});

// Opt a server-rendered table in with `data-tabulator`. Everything else comes
// from `tabulator-*` attributes on the <table> and its <th> elements, so
// adding a table needs no JavaScript of its own. Tabulator takes column
// titles from the header text and derives each field from it ("Total Size"
// becomes `total_size`), and takes cell values from the cell's innerHTML.
// Columns carrying links or badges need `tabulator-formatter="html"` to render
// as markup rather than as escaped text; only reach for it where the cell holds
// template-rendered markup, since the value is re-injected as innerHTML.
//
// `tabulator-responsiveLayout="collapse"` folds columns that do not fit into a
// labelled block under each row, ordered by per-column `tabulator-responsive`
// priorities (higher numbers fold first). It has no effect under
// `tabulator-layout="fitColumns"`, which shrinks columns instead of ever
// overflowing — pair it with `fitDataFill`.
document.querySelectorAll("table[data-tabulator]").forEach(function (table) {
  new Tabulator(table);
});
