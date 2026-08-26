/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, describe, it, beforeEach, jest */

/**
 * Tests for the declarative admin tables, asserting on runtime behavior rather
 * than on the markup that configures it.
 *
 * A `tabulator-*` attribute can be spelled correctly and still have no effect:
 * Tabulator parses those inside HtmlTableImport, which initializes after the
 * core modules and after GroupRows has decided whether to subscribe, so any
 * table option consulted during a module's `initialize()` never sees one.
 * Asserting that an attribute is present therefore proves nothing about
 * whether the table does what it says.
 */

async function render(html) {
  document.body.innerHTML = html;
  let table;
  await jest.isolateModulesAsync(async () => {
    const { TabulatorFull } = await import("tabulator-tables");
    await import("../../warehouse/admin/static/js/tabulator");
    const mounted = document.querySelector(".tabulator") || document.querySelector("table");
    table = TabulatorFull.findTable(mounted)[0];
  });
  await new Promise((resolve) => {
    table.on("tableBuilt", resolve);
    if (table.initialized) {
      resolve();
    }
  });
  return table;
}

const GROUPED = `
  <table data-tabulator
         tabulator-layout="fitDataFill"
         tabulator-groupBy="project_name"
         tabulator-pagination="true"
         tabulator-paginationSize="25"
         tabulator-paginationSizeSelector="25,50,100">
    <thead><tr>
      <th tabulator-visible="false">Project Name</th><th>Summary</th>
    </tr></thead>
    <tbody>
      <tr><td><a href="/admin/projects/evil-pkg/">evil-pkg</a></td><td>one</td></tr>
      <tr><td><a href="/admin/projects/evil-pkg/">evil-pkg</a></td><td>two</td></tr>
      <tr><td><a href="/admin/projects/gone-pkg/">gone-pkg</a></td><td>three</td></tr>
    </tbody>
  </table>`;

describe("declarative admin tables", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("groups rows by a hidden column", async () => {
    const table = await render(GROUPED);
    // Grouping is the only thing rendering the project name on the malware
    // reports page, since its column is hidden.
    expect(table.getGroups()).toHaveLength(2);
    expect(table.getColumns()[0].isVisible()).toBe(false);
  });

  it("applies the layout mode named in the attribute", async () => {
    const table = await render(GROUPED);
    expect(table.modules.layout.mode).toBe("fitDataFill");
  });

  it("gives list and number options their real types", async () => {
    const table = await render(GROUPED);
    expect(table.options.paginationSize).toBe(25);
    expect(table.options.paginationSizeSelector).toEqual([25, 50, 100]);
  });

  it("sorts on the text of a cell rather than its markup", async () => {
    // Cell values are markup, so a naive sort compares hrefs.
    const table = await render(`
      <table data-tabulator><thead><tr><th>Name</th></tr></thead>
        <tbody>
          <tr><td><a href="/admin/sponsors/ffffffff/">Aardvark</a></td></tr>
          <tr><td><a href="/admin/sponsors/00000000/">Zebra</a></td></tr>
        </tbody></table>`);
    table.setSort("name", "asc");
    const names = table
      .getData("active")
      .map((row) => row.name.replace(/<[^>]*>/g, "").trim());
    // Sorting the markup would lead with Zebra, whose href sorts first.
    expect(names).toEqual(["Aardvark", "Zebra"]);
  });

  it.each([
    ["asc", ["Gold", "Silver"]],
    ["desc", ["Silver", "Gold"]],
  ])("sorts blanks last going %s", async (dir, filled) => {
    // A column of optional values keeps its filled-in rows together.
    const table = await render(`
      <table data-tabulator><thead><tr><th>Level</th></tr></thead>
        <tbody>
          <tr><td>Gold</td></tr><tr><td></td></tr><tr><td>Silver</td></tr>
        </tbody></table>`);
    table.setSort("level", dir);
    expect(table.getData("active").map((row) => row.level)).toEqual([...filled, ""]);
  });

  it("filters a column on its text, and skips columns opted out", async () => {
    const table = await render(`
      <table data-tabulator>
        <thead><tr>
          <th>Name</th><th tabulator-headerFilter="false">Active?</th>
        </tr></thead>
        <tbody>
          <tr><td><a href="/admin/sponsors/beeeee/">Aardvark</a></td>
              <td><i class="fa fa-check"></i></td></tr>
          <tr><td><a href="/admin/sponsors/aaaaaa/">Zebra</a></td>
              <td><i class="fa fa-times"></i></td></tr>
        </tbody></table>`);

    const [name, active] = table.getColumns();
    expect(name.getDefinition().headerFilter).toBe("input");
    // An icon column has no text to match, so a filter box there could only
    // ever empty the table.
    expect(active.getDefinition().headerFilter).toBe(false);

    // "beeeee" appears only inside the href, so a filter reading the markup
    // would answer with Aardvark for a string nobody can see on the page.
    table.setHeaderFilterValue("name", "beeeee");
    expect(table.getData("active")).toEqual([]);

    table.setHeaderFilterValue("name", "aardvark");
    const shown = table
      .getData("active")
      .map((row) => row.name.replace(/<[^>]*>/g, "").trim());
    expect(shown).toEqual(["Aardvark"]);
  });

  it("toggles a column once per click of its menu entry", async () => {
    const table = await render(`
      <table data-tabulator data-tabulator-column-menu>
        <thead><tr><th tabulator-visible="false">IP address</th><th>Event</th></tr></thead>
        <tbody><tr><td>127.0.0.1</td><td>login</td></tr></tbody></table>`);
    const column = table.getColumns()[0];
    const [entry] = table.options.columnDefaults.headerMenu.call(table);

    // Tabulator listens on the menu item, so a <label> here would forward a
    // second click to its own checkbox and toggle the column straight back.
    const item = document.createElement("div");
    item.appendChild(entry.label);
    document.body.appendChild(item);
    item.addEventListener("click", (event) => entry.action(event, column));
    entry.label.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    expect(column.isVisible()).toBe(true);
  });
  it("shows a column the responsive layout folded as still wanted", async () => {
    const table = await render(`
      <table data-tabulator data-tabulator-column-menu
             tabulator-responsiveLayout="collapse">
        <thead><tr><th>Event</th><th tabulator-responsive="2">User-Agent</th></tr></thead>
        <tbody><tr><td>login</td><td>curl/8.0</td></tr></tbody></table>`);
    const agent = table
      .getColumns()
      .find((column) => column.getDefinition().title === "User-Agent");

    // What a narrow window does: fold the column into the collapsed block.
    table.modules.responsiveLayout.hideColumn(agent);
    expect(agent.isVisible()).toBe(false);

    const entry = table.options.columnDefaults.headerMenu
      .call(table)
      .find((item) => item.label.textContent.trim() === "User-Agent");
    // Reading `isVisible()` here would report a folded column as one the
    // admin had hidden, and clicking it would then show it rather than hide.
    expect(entry.label.querySelector("input").checked).toBe(true);
  });

  it("gives a collapsing table a handle to close the block with", async () => {
    const table = await render(`
      <table data-tabulator tabulator-responsiveLayout="collapse">
        <thead><tr><th>Event</th></tr></thead>
        <tbody><tr><td>login</td></tr></tbody></table>`);

    // ResponsiveLayout wires up a toggle only when it finds this formatter,
    // and no attribute can ask for it, so without one the collapsed block
    // renders permanently open with nothing to close it.
    const [handle] = table.getColumns();
    expect(handle.getDefinition().formatter).toBe("responsiveCollapse");
    expect(table.modules.responsiveLayout.collapseHandleColumn).toBeTruthy();
    // No title, so it stays out of the column visibility menu.
    expect(handle.getDefinition().title).toBeUndefined();
  });

  it("ignores an attribute naming only an Object prototype member", async () => {
    // HTML lowercases attribute names, so `constructor` and `__proto__` reach
    // the prototype chain of the option table and answer with something that
    // is not an option at all.
    document.body.innerHTML = `
      <table id="first" data-tabulator tabulator-constructor="boom">
        <thead><tr><th>Name</th></tr></thead>
        <tbody><tr><td>a</td></tr></tbody></table>
      <table id="second" data-tabulator>
        <thead><tr><th>Name</th></tr></thead>
        <tbody><tr><td>b</td></tr></tbody></table>`;
    await jest.isolateModulesAsync(async () => {
      await import("../../warehouse/admin/static/js/tabulator");
    });
    await new Promise((resolve) => setTimeout(resolve));

    // Both tables built: a throw while reading the first one's attributes
    // would have left the second as a plain <table>.
    expect(document.querySelectorAll("div.tabulator")).toHaveLength(2);
  });

  it("exports what a cell shows rather than the markup showing it", async () => {
    const table = await render(`
      <table id="sponsors" data-tabulator data-tabulator-download>
        <thead><tr><th>Name</th></tr></thead>
        <tbody><tr><td><a href="/admin/sponsors/00000000/">Aardvark</a></td></tr>
        </tbody></table>`);

    const { accessorDownload, accessorClipboard } = table.options.columnDefaults;
    const cell = "<a href=\"/admin/sponsors/00000000/\">Aardvark</a>";
    expect(accessorDownload(cell)).toBe("Aardvark");
    expect(accessorClipboard(cell)).toBe("Aardvark");

    const download = jest.spyOn(table, "download").mockImplementation(() => {});
    const copy = jest.spyOn(table, "copyToClipboard").mockImplementation(() => {});
    const [copyButton, csvButton] = document.querySelectorAll(
      "div.btn-group > button",
    );
    copyButton.click();
    csvButton.click();

    // Filtered and sorted as they stand, across every page, which is what the
    // DataTables toolbar these replace exported.
    expect(copy).toHaveBeenCalledWith("active");
    // Without this the Clipboard module never binds the listener that
    // `copyToClipboard` fires against, and the button does nothing at all.
    expect(table.options.clipboard).toBe("copy");
    expect(download).toHaveBeenCalledWith("csv", "sponsors.csv", {}, "active");
  });

  it("leaves the export buttons off a table that did not ask for them", async () => {
    await render(`
      <table data-tabulator><thead><tr><th>Name</th></tr></thead>
        <tbody><tr><td>a</td></tr></tbody></table>`);
    expect(document.querySelector("div.btn-group")).toBeNull();
  });
});
