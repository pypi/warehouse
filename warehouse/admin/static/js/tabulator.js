/* SPDX-License-Identifier: Apache-2.0 */

import { TabulatorFull as Tabulator } from "tabulator-tables";

import filesize from "./utils/filesize";

// Cells hold raw byte counts so `tabulator-sorter="number"` orders them
// correctly, while the column still displays a human-readable size.
Tabulator.extendModule("format", "formatters", {
  filesize: (cell) => filesize(cell.getValue()),
});

// A cell's value is the markup the template rendered into it, so anything
// comparing values — sorting, filtering — has to read the text out first,
// or it compares `href`s and CSS class names instead of what is on screen.
//
// Sorting asks for the same handful of values O(n log n) times, and parsing
// HTML is far and away the expensive part, so results are memoized. The cache
// is keyed by the markup itself and shared by every table on the page, so it
// is capped rather than left to grow: rows come and go as an admin filters or
// pages, and nothing would ever drop the entries they leave behind. Refilling
// it costs one parse per cell on screen, so it is emptied wholesale.
const CELL_TEXT_CACHE_LIMIT = 4096;
const cellTextCache = new Map();

function cellText(value) {
  if (typeof value !== "string") {
    return value == null ? "" : String(value);
  }
  if (!value.includes("<") && !value.includes("&")) {
    return value.trim();
  }
  let text = cellTextCache.get(value);
  if (text === undefined) {
    const holder = document.createElement("div");
    holder.innerHTML = value;
    text = holder.textContent.trim();
    if (cellTextCache.size >= CELL_TEXT_CACHE_LIMIT) {
      cellTextCache.clear();
    }
    cellTextCache.set(value, text);
  }
  return text;
}

Tabulator.extendModule("sort", "sorters", {
  // Numbers embedded in text sort as numbers, so "10" follows "9".
  //
  // Blanks sort to the bottom in either direction, so a column of optional
  // values keeps the filled-in rows together. The sort module swaps its
  // operands for a descending sort rather than negating the result, so
  // holding blanks down means answering relative to `dir`.
  text: (a, b, aRow, bRow, column, dir) => {
    const left = cellText(a);
    const right = cellText(b);
    if (!left || !right) {
      if (left === right) {
        return 0;
      }
      const blankLast = dir === "asc" ? 1 : -1;
      return left ? -blankLast : blankLast;
    }
    return left.localeCompare(right, undefined, {
      numeric: true,
      sensitivity: "base",
    });
  },
});

// Opt a server-rendered table in with `data-tabulator`. Everything else comes
// from `tabulator-*` attributes on the <table> and its <th> elements, so
// adding a table needs no JavaScript of its own. Tabulator takes column
// titles from the header text and derives each field from it ("Total Size"
// becomes `total_size`), and takes cell values from the cell's innerHTML.
//
// Tabulator can read `tabulator-*` attributes itself, but only from inside
// the HtmlTableImport module, which initializes after the core modules and
// after GroupRows has already decided whether to subscribe to anything. Any
// option consulted during a module's `initialize()` — `layout`, `groupBy` —
// is therefore read before the attribute is parsed, and silently keeps its
// default. Table options are parsed here instead and handed to the
// constructor, which is also where they get the right type: attributes are
// strings, and Tabulator only ever coerces "true" and "false".
//
// Column options stay with Tabulator, since those are consumed later, when
// the columns are built. They are still strings, so `tabulator-responsive`
// priorities compare numerically but cannot be a real `0`, the one value
// that would exclude a column from responsive folding altogether.
//
// Unmarked columns default to 1, and columns sharing a priority fold
// rightmost first, so number every column that should fold before them with
// a 2 or higher. Marking one `1` says nothing and leaves it to fold by
// position.
const TABLE_OPTIONS = {
  layout: ["layout", String],
  height: ["height", String],
  responsivelayout: ["responsiveLayout", String],
  placeholder: ["placeholder", String],
  groupby: ["groupBy", String],
  pagination: ["pagination", (v) => v !== "false"],
  paginationsize: ["paginationSize", Number],
  paginationsizeselector: [
    "paginationSizeSelector",
    (v) => v.split(",").map(Number),
  ],
};

function tableOptions(table) {
  const options = {};
  const consumed = [];

  for (const attribute of Array.from(table.attributes)) {
    if (!attribute.name.startsWith("tabulator-")) {
      continue;
    }
    // `hasOwn`, since HTML lowercases attribute names and a plain lookup on an
    // object literal answers for `constructor` and `__proto__` too.
    const name = attribute.name.slice("tabulator-".length);
    if (Object.hasOwn(TABLE_OPTIONS, name)) {
      const [option, parse] = TABLE_OPTIONS[name];
      options[option] = parse(attribute.value);
      consumed.push(attribute.name);
    }
  }

  // HtmlTableImport parses these attributes too, late and as strings, and
  // would put `paginationSize: "25"` back over the number parsed here.
  // Removing them once read leaves this the only reader.
  consumed.forEach((name) => table.removeAttribute(name));
  return options;
}

// Whether an admin has asked to see a column, seeded from the markup.
//
// Deliberately not `column.isVisible()`: ResponsiveLayout hides a column it
// folds into the collapsed block, so on a narrow window that answers false for
// columns the admin never touched. The menu would then report a folded column
// as one they had hidden, and clicking it would show it rather than hide it.
const columnWanted = new WeakMap();

function isColumnWanted(column) {
  if (!columnWanted.has(column)) {
    columnWanted.set(column, column.getDefinition().visible !== false);
  }
  return columnWanted.get(column);
}

// Put ResponsiveLayout's fold cursor back in step with its column list.
//
// Showing or hiding a column rebuilds that list and the record of which
// columns are folded, but leaves `index` — the position it folds from — where
// it was, so the next resize folds or unfolds whichever column now sits at the
// stale index. Everything ahead of the cursor is folded, which is exactly what
// the rebuilt list of folded columns counts.
function resyncResponsiveFold(table) {
  const responsive = table.modules.responsiveLayout;
  if (responsive) {
    responsive.index = responsive.hiddenColumns.length;
  }
}

// Build the column list for a header menu, checked to match what the admin
// asked for. Tabulator calls this with the table as `this` each time a menu
// opens, so the checkboxes always reflect the columns as they stand.
function columnVisibilityMenu() {
  const table = this;

  return table
    .getColumns()
    .filter((column) => column.getDefinition().title)
    .map((column) => {
      // Deliberately not a <label>: Tabulator listens on the menu item, and a
      // label would forward a second click to its own checkbox, toggling the
      // column straight back.
      const item = document.createElement("span");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = isColumnWanted(column);
      checkbox.tabIndex = -1;
      item.appendChild(checkbox);
      item.appendChild(
        document.createTextNode(` ${column.getDefinition().title}`),
      );

      return {
        label: item,
        action: function (event) {
          // Without this the menu closes on the first click, which makes
          // hiding several columns needlessly tedious.
          event.stopPropagation();
          const wanted = !isColumnWanted(column);
          columnWanted.set(column, wanted);
          if (wanted) {
            column.show();
          } else {
            column.hide();
          }
          checkbox.checked = wanted;
          resyncResponsiveFold(table);
        },
      };
    });
}

// ResponsiveLayout wires up a collapse toggle only when it finds a column
// using its own `responsiveCollapse` formatter, and no `tabulator-*` attribute
// can declare one — the formatter comes from the module rather than from the
// markup. Without it `responsiveLayoutCollapseStartOpen` leaves the folded
// block open under every row with no control to close it, so a collapsing
// table gets the column added here.
const COLLAPSE_HANDLE_COLUMN = {
  formatter: "responsiveCollapse",
  width: 30,
  minWidth: 30,
  hozAlign: "center",
  resizable: false,
  headerSort: false,
  headerFilter: false,
  // No title, which also keeps it out of the column visibility menu.
  headerMenu: false,
  // Never fold the control that unfolds everything else.
  responsive: 0,
  download: false,
  clipboard: false,
};

// Restore the CSV and copy exports the DataTables toolbars carried, using
// Tabulator's own Download and Clipboard modules. Both run over the rows as
// filtered and sorted, across every page, which is the scope DataTables
// exported. See https://www.tabulator.info/docs/6.x/download.
function toolbarButton(label, iconClass, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-outline-secondary";
  const icon = document.createElement("i");
  icon.className = `fa ${iconClass}`;
  button.appendChild(icon);
  button.appendChild(document.createTextNode(` ${label}`));
  button.addEventListener("click", onClick);
  return button;
}

function exportToolbar(table, filename) {
  const toolbar = document.createElement("div");
  toolbar.className = "btn-group btn-group-sm mb-2";
  toolbar.appendChild(
    toolbarButton("Copy", "fa-copy", () => table.copyToClipboard("active")),
  );
  toolbar.appendChild(
    toolbarButton("CSV", "fa-download", () =>
      table.download("csv", `${filename}.csv`, {}, "active"),
    ),
  );
  return toolbar;
}

function mountTable(element) {
  const options = tableOptions(element);

  options.columnDefaults = {
    // Cell values are read out of the DOM as innerHTML, so they arrive
    // already escaped by the template. Tabulator's default `plaintext`
    // formatter escapes them a second time, which shows `&`, `<` and `>` as
    // literal entities and renders links and badges as their own source.
    // Re-injecting the same markup as innerHTML round-trips it exactly.
    // A column needing real formatting overrides this, e.g.
    // `tabulator-formatter="filesize"`.
    //
    // THE RULE THIS RESTS ON: a `data-tabulator` cell must contain only
    // Jinja-autoescaped output. Never `|safe`, `Markup`, or anything else
    // carrying unescaped user input into one of these tables — the value is
    // re-injected as HTML. Group headings and the responsive-collapse block
    // do that regardless of the formatter, so the rule holds for every
    // column, not just the ones rendered here.
    formatter: "html",
    // Sort and filter on what the cell shows rather than on its markup.
    sorter: "text",
    // A box under each column heading, so it is obvious which column a
    // search applies to. Columns where a text match would mislead — an icon
    // with no text, an action button, a size rendered from a raw byte count —
    // opt out with `tabulator-headerFilter="false"`.
    headerFilter: "input",
    headerFilterPlaceholder: "filter",
    headerFilterFunc: (headerValue, rowValue) =>
      cellText(rowValue).toLowerCase().includes(String(headerValue).toLowerCase()),
    // Tabulator sizes a column to its widest cell, so one long payload or
    // caveat blob would otherwise push every other column off screen. Capped
    // and wrapped rather than capped and clipped, since a payload an admin
    // cannot finish reading is the whole reason these columns are on the page.
    // Admins can still drag a column wider.
    maxInitialWidth: 480,
    variableHeight: true,
    // Exports carry what the cell shows, not the markup showing it.
    accessorDownload: cellText,
    accessorClipboard: cellText,
  };

  if (options.responsiveLayout === "collapse") {
    // HtmlTableImport appends the columns it reads from the <th>s to whatever
    // is here already, so the handle lands first.
    options.columns = [{ ...COLLAPSE_HANDLE_COLUMN }];
  }

  // Opt in with `data-tabulator-column-menu` to hang a column list off every
  // header, which is how an admin reaches a `tabulator-visible="false"`
  // column. Left off by default, since it puts an icon in every header.
  if (element.dataset.tabulatorColumnMenu !== undefined) {
    options.columnDefaults.headerMenu = columnVisibilityMenu;
  }

  // Opt in with `data-tabulator-download` for the copy and CSV buttons.
  const exporting = element.dataset.tabulatorDownload !== undefined;
  if (exporting) {
    // "copy" rather than true: the Clipboard module binds the copy listener
    // `copyToClipboard` fires against only once this is set, and true would
    // also have it read pastes into the table, which no admin table wants.
    options.clipboard = "copy";
  }

  const table = new Tabulator(element, options);

  if (exporting) {
    const filename = element.id || "export";
    table.on("tableBuilt", () => {
      table.element.parentNode.insertBefore(
        exportToolbar(table, filename),
        table.element,
      );
    });
  }
}

document.querySelectorAll("table[data-tabulator]").forEach(function (element) {
  try {
    mountTable(element);
  } catch (error) {
    // A bad attribute on one table is that table's problem alone. Letting it
    // out of the loop would leave every table after it on the page as a plain
    // <table> — no sorting, no filtering, no paging — and users/detail.html
    // mounts five. Tabulator defers the build itself, so what this covers is
    // reading the options and handing them over.
    console.error("Could not build admin table", element, error);
  }
});
