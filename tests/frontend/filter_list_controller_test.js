/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it, jest */


import {Application} from "@hotwired/stimulus";
import FilterListController from "../../warehouse/static/js/warehouse/controllers/filter_list_controller";
import AttestationsViewerController from "../../warehouse/static/js/warehouse/controllers/attestations_viewer_controller";
import {delay} from "./utils";


const testFixtureHTMLVisibilityToggle = `
<p id="initial-toggle-visibility-shown" class="hidden initial-toggle-visibility">
    Initially hidden, should end up shown.
</p>
<p id="initial-toggle-visibility-hidden" class="initial-toggle-visibility">
    Initially shown, should end up hidden.
</p>
`;
const testFixtureHTMLShowing = `
<p id="shown-and-total" data-filter-list-target="summary"></p>
`;
const testFixtureHTMLFilters = `
<input id="filter-input-description" type="text" data-action="filter-list#filter"
    data-filter-list-target="filter" data-filtered-source="description" data-comparison-type="includes"
    data-auto-update-url-querystring="false">
<select id="filter-select-myattr" data-action="filter-list#filter"
    data-filter-list-target="filter" data-filtered-source="myattr" data-comparison-type="exact"
    data-auto-update-url-querystring="true">
  <option value="" selected>My Attrs</option>
  <option value="myattr1">myattr 1</option>
  <option value="myattr2">myattr 2</option>
  <option value="myattr3">myattr 3</option>
</select>
<select id="filter-select-contentType" data-action="filter-list#filter"
    data-filter-list-target="filter" data-filtered-source="contentType" data-comparison-type="exact"
    data-auto-update-url-querystring="true">
  <option value="" selected>Content Types</option>
  <option value="contentType1">Content Type 1</option>
  <option value="contentType2">Content Type 2</option>
  <option value="contentType3">Content Type 3</option>
</select>
`;
const testFixtureHTMLRadioFilters = `
<a id="radio-filter-clear" href="#" data-action="filter-list#filterClear"
    data-filter-list-target="clear" class="hidden">Clear filters</a>
<button id="radio-filter-trigger" type="button" data-filter-list-target="trigger">
  <span id="radio-filter-count" class="hidden" data-filter-list-target="count"></span>
</button>
<input id="filter-radio-color-red" type="radio" name="color" value="red" data-action="filter-list#filter"
    data-filter-list-target="filter" data-filtered-source="color" data-comparison-type="exact"
    data-auto-update-url-querystring="true">
<input id="filter-radio-color-blue" type="radio" name="color" value="blue" data-action="filter-list#filter"
    data-filter-list-target="filter" data-filtered-source="color" data-comparison-type="exact"
    data-auto-update-url-querystring="true">
`;
const testFixtureHTMLRadioItems = `
<div id="ritem-1" class="my-radio-item" data-filter-list-target="item" data-filtered-target-color='["red"]'>Item 1</div>
<div id="ritem-2" class="my-radio-item" data-filter-list-target="item" data-filtered-target-color='["blue"]'>Item 2</div>
`;
const testFixtureHTMLItems = `
        <a id="url-update" href="http://localhost#testing" data-filter-list-target="url"></a>
        <a id="filter-clear" href="#" data-action="filter-list#filterClear">Show all files</a>
        <div id="item-1" class="my-item" data-filter-list-target="item"
            data-filtered-target-description='["Description 1","Content Type 1", "My Attr 1"]'
            data-filtered-target-content-type='["contentType1"]'
            data-filtered-target-myattr='["myattr1"]'>Item 1</div>
        <div id="item-2" class="my-item" data-filter-list-target="item"
            data-filtered-target-description='["Description 2","Content Type 2", "My Attr 2"]'
            data-filtered-target-content-type='["contentType2"]'
            data-filtered-target-myattr='["myattr2"]'>Item 2</div>
        <div id="item-3" class="my-item" data-filter-list-target="item"
            data-filtered-target-description='["Description 3","Content Type 3", "My Attr 3"]'
            data-filtered-target-content-type='["contentType3"]'
            data-filtered-target-myattr='["myattr3"]'>Item 3</div>
`;


describe("Filter list controller", () => {
  const setFilterSelectValue = function (filterId, value) {
    const elFilter = document.getElementById(filterId);
    const dispatchEventSpy = jest.spyOn(elFilter, "dispatchEvent");

    elFilter.value = value;

    // Manually trigger the 'change' event to get the MutationObserver that Stimulus uses to be updated.
    // Also ensure the event has been dispatched.
    const event = new Event("change");
    elFilter.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
    return elFilter;
  };
  const setFilterInputValue = function (filterId, value) {
    const elFilter = document.getElementById(filterId);
    const dispatchEventSpy = jest.spyOn(elFilter, "dispatchEvent");

    elFilter.value = value;

    // Manually trigger the 'input' event to get the MutationObserver that Stimulus uses to be updated.
    // Also ensure the event has been dispatched.
    const event = new Event("input");
    elFilter.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
  };
  const clearFilters = function () {
    const elUrl = document.getElementById("filter-clear");
    const dispatchEventSpy = jest.spyOn(elUrl, "dispatchEvent");
    const event = new Event("click");
    elUrl.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
  };
  const expectedSelectOptions = function (filterId, values) {
    const filterMyAttr = document.getElementById(filterId);
    expect(filterMyAttr.options).toHaveLength(values.length);
    expect(Array.from(filterMyAttr.options).map(option => [option.value, option.selected])).toEqual(values);
  };
  const appStart = async function () {
    const div = document.createElement("div");
    div.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLVisibilityToggle}
        ${testFixtureHTMLShowing}
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;
    document.body.appendChild(div);

    const application = Application.start();
    application.register("filter-list", FilterListController);

    // wait for app to be ready
    await delay(30);

    return application;
  };
  const appStop = function (application) {
    application.stop();
  };

  beforeEach(() => {
    // console.log(`Start test ${expect.getState().currentTestName}`);
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "http://localhost/#testing");
  });
  afterEach(() => {
    document.body.innerHTML = "";
  });

  describe("loads filter from url",  () => {
    it("should use the querystring", async () => {
      const url = "http://localhost/?description=1&myattr=myattr1&contentType=contentType1#testing";
      window.history.replaceState({}, "", decodeURIComponent(url));

      const application = await appStart();

      expect(document.location.href).toEqual("http://localhost/?myattr=myattr1&contentType=contentType1#testing");

      expectedSelectOptions("filter-select-myattr", [
        ["", false], ["myattr1", true], ["myattr2", false], ["myattr3", false],
      ]);
      expectedSelectOptions("filter-select-contentType", [
        ["", false], ["contentType1", true], ["contentType2", false], ["contentType3", false],
      ]);
      expect(document.getElementById("filter-input-description").value).toEqual("");


      const elP = document.getElementById("url-update");
      expect(elP.href).toEqual("http://localhost/?myattr=myattr1&contentType=contentType1#testing");

      expect(document.getElementsByClassName("my-item").length).toEqual(3);
      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).not.toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

      appStop(application);
    });
  });

  it("has expected items and filters on initialization", async () => {
    const application = await appStart();

    const elController = document.getElementById("controller");
    const controller = application.getControllerForElementAndIdentifier(elController, "filter-list");

    expect(controller.itemTargets).toHaveLength(3);
    expect(controller.itemTargets[0]).toHaveTextContent("Item 1");
    expect(controller.itemTargets[1]).toHaveTextContent("Item 2");
    expect(controller.itemTargets[2]).toHaveTextContent("Item 3");

    expect(controller.filterTargets).toHaveLength(3);
    expect(controller.filterTargets[0].id).toEqual("filter-input-description");
    expect(controller.filterTargets[1].id).toEqual("filter-select-myattr");
    expect(controller.filterTargets[2].id).toEqual("filter-select-contentType");

    expect(Object.keys(controller.initialItemFilterData)).toHaveLength(3);
    expect(controller.initialItemFilterData["0"]).toEqual({
      "contentType": ["contentType1"],
      "myattr": ["myattr1"],
      "description": ["Description 1", "Content Type 1", "My Attr 1"],
    });
    expect(controller.initialItemFilterData["1"]).toEqual({
      "contentType": ["contentType2"],
      "myattr": ["myattr2"],
      "description": ["Description 2", "Content Type 2", "My Attr 2"],
    });
    expect(controller.initialItemFilterData["2"]).toEqual({
      "contentType": ["contentType3"],
      "myattr": ["myattr3"],
      "description": ["Description 3", "Content Type 3", "My Attr 3"],
    });

    const elP = document.getElementById("url-update");
    expect(elP.href).toEqual("http://localhost/#testing");
    expect(document.location.href).toEqual("http://localhost/#testing");

    appStop(application);
  });

  it("makes expected elements visible by toggling visibility", async () => {
    const application = await appStart();

    const elShown = document.getElementById("initial-toggle-visibility-shown");
    expect(elShown.classList).not.toContain("hidden");

    const elHidden = document.getElementById("initial-toggle-visibility-hidden");
    expect(elHidden.classList).toContain("hidden");

    appStop(application);
  });

  it("toggling visibility is scoped per controller instance, not document-wide", async () => {
    // Two independent filter-list controllers on the same page (e.g. the Files tab's wheel
    // search and the Security tab's attestations viewer) must not re-toggle each other's
    // progressive-enhancement markup.
    document.body.innerHTML = `
      <div id="controller-a" data-controller="filter-list">
        <div id="shown-a" class="hidden initial-toggle-visibility"></div>
      </div>
      <div id="controller-b" data-controller="filter-list">
        <div id="shown-b" class="hidden initial-toggle-visibility"></div>
      </div>
    `;

    const application = Application.start();
    application.register("filter-list", FilterListController);
    await delay(30);

    expect(document.getElementById("shown-a").classList).not.toContain("hidden");
    expect(document.getElementById("shown-b").classList).not.toContain("hidden");

    appStop(application);
  });

  it("has expected count when all items begin shown", async () => {
    const application = await appStart();

    expectedSelectOptions("filter-select-myattr", [
      ["", true], ["myattr1", false], ["myattr2", false], ["myattr3", false],
    ]);
    expectedSelectOptions("filter-select-contentType", [
      ["", true], ["contentType1", false], ["contentType2", false], ["contentType3", false],
    ]);
    expect(document.getElementById("filter-input-description").value).toEqual("");

    const elUrl = document.getElementById("url-update");
    expect(elUrl.href).toEqual("http://localhost/#testing");
    expect(document.location.href).toEqual("http://localhost/#testing");

    const elP = document.getElementById("shown-and-total");
    expect(document.getElementsByClassName("my-item").length).toEqual(3);
    expect(elP.textContent).toEqual("Showing 3 of 3 built distribution (wheel) files.");

    appStop(application);
  });
  it("filter by input text updates the item classes", async () => {
    const application = await appStart();

    setFilterSelectValue("filter-select-myattr", "");
    setFilterSelectValue("filter-select-contentType", "");
    setFilterInputValue("filter-input-description", "2");

    const elP = document.getElementById("url-update");
    expect(elP.href).toEqual("http://localhost/#testing");
    expect(document.location.href).toEqual("http://localhost/#testing");

    expectedSelectOptions("filter-select-myattr", [
      ["", true], ["myattr2", false],
    ]);
    expectedSelectOptions("filter-select-contentType", [
      ["", true], ["contentType2", false],
    ]);

    expect(document.getElementsByClassName("my-item").length).toEqual(3);
    const elItem1 = document.getElementById("item-1");
    expect(elItem1.classList).toContainEqual("hidden");

    const elItem2 = document.getElementById("item-2");
    expect(elItem2.classList).not.toContainEqual("hidden");

    const elItem3 = document.getElementById("item-3");
    expect(elItem3.classList).toContainEqual("hidden");

    appStop(application);
  });
  it("shows all items after clearing the input text filter", async () => {
    const application = await appStart();

    setFilterSelectValue("filter-select-myattr", "myattr2");
    setFilterSelectValue("filter-select-contentType", "");
    setFilterInputValue("filter-input-description", "lizards");

    expectedSelectOptions("filter-select-myattr", [
      ["", false], ["myattr1", false], ["myattr2", true], ["myattr3", false],
    ]);
    expectedSelectOptions("filter-select-contentType", [
      ["", true],
    ]);

    const elP1 = document.getElementById("shown-and-total");
    expect(elP1.textContent).toEqual("No built distributions (wheels) match the current filters. Showing 0 of 3 built distribution (wheel) files.");

    const elUrl = document.getElementById("url-update");
    expect(elUrl.href).toEqual("http://localhost/?myattr=myattr2#testing");
    expect(document.location.href).toEqual("http://localhost/?myattr=myattr2#testing");

    const elItem1 = document.getElementById("item-1");
    expect(elItem1.classList).toContainEqual("hidden");

    const elItem2 = document.getElementById("item-2");
    expect(elItem2.classList).toContainEqual("hidden");

    const elItem3 = document.getElementById("item-3");
    expect(elItem3.classList).toContainEqual("hidden");

    clearFilters();

    expect(elP1.textContent).toEqual("Showing 3 of 3 built distribution (wheel) files.");
    expect(elUrl.href).toEqual("http://localhost/#testing");
    expect(document.location.href).toEqual("http://localhost/#testing");

    expectedSelectOptions("filter-select-myattr", [
      ["", true], ["myattr1", false], ["myattr2", false], ["myattr3", false],
    ]);
    expectedSelectOptions("filter-select-contentType", [
      ["", true], ["contentType1", false], ["contentType2", false], ["contentType3", false],
    ]);

    const elP2 = document.getElementById("shown-and-total");
    expect(elP2.textContent).toEqual("Showing 3 of 3 built distribution (wheel) files.");

    expect(elItem1.classList).not.toContainEqual("hidden");
    expect(elItem2.classList).not.toContainEqual("hidden");
    expect(elItem3.classList).not.toContainEqual("hidden");

    appStop(application);
  });

  it("selecting an option filters the items and updates the classes", async () => {
    const application = await appStart();

    setFilterSelectValue("filter-select-myattr", "myattr3");
    setFilterSelectValue("filter-select-contentType", "");
    setFilterInputValue("filter-input-description", "");

    expectedSelectOptions("filter-select-myattr", [
      ["", false], ["myattr1", false], ["myattr2", false], ["myattr3", true],
    ]);
    expectedSelectOptions("filter-select-contentType", [
      ["", true], ["contentType3", false],
    ]);

    const elP = document.getElementById("url-update");
    expect(elP.href).toEqual("http://localhost/?myattr=myattr3#testing");
    expect(document.location.href).toEqual("http://localhost/?myattr=myattr3#testing");

    const elItem1 = document.getElementById("item-1");
    expect(elItem1.classList).toContainEqual("hidden");

    const elItem2 = document.getElementById("item-2");
    expect(elItem2.classList).toContainEqual("hidden");

    const elItem3 = document.getElementById("item-3");
    expect(elItem3.classList).not.toContainEqual("hidden");

    appStop(application);
  });

  describe("radio button filters", () => {
    const setFilterRadioChecked = function (filterId, checked) {
      const elFilter = document.getElementById(filterId);
      const dispatchEventSpy = jest.spyOn(elFilter, "dispatchEvent");

      elFilter.checked = checked;

      // Stimulus's default action event for any <input> (including radio/checkbox) is "input";
      // real browsers dispatch both "input" and "change" when a radio/checkbox is toggled.
      const event = new Event("input");
      elFilter.dispatchEvent(event);
      expect(dispatchEventSpy).toHaveBeenCalledWith(event);
      return elFilter;
    };
    const clearRadioFilters = function () {
      const elClear = document.getElementById("radio-filter-clear");
      const dispatchEventSpy = jest.spyOn(elClear, "dispatchEvent");
      const event = new Event("click");
      elClear.dispatchEvent(event);
      expect(dispatchEventSpy).toHaveBeenCalledWith(event);
    };
    const appStartRadio = async function () {
      const div = document.createElement("div");
      div.innerHTML = `
        <div id="radio-controller" data-controller="filter-list">
          ${testFixtureHTMLRadioFilters}
          ${testFixtureHTMLRadioItems}
        </div>
        `;
      document.body.appendChild(div);

      const application = Application.start();
      application.register("filter-list", FilterListController);

      await delay(30);

      return application;
    };

    it("shows all items and unchecked radios by default", async () => {
      const application = await appStartRadio();

      expect(document.getElementById("filter-radio-color-red").checked).toEqual(false);
      expect(document.getElementById("filter-radio-color-blue").checked).toEqual(false);
      expect(document.getElementById("ritem-1").classList).not.toContainEqual("hidden");
      expect(document.getElementById("ritem-2").classList).not.toContainEqual("hidden");
      expect(document.getElementById("radio-filter-clear").classList).toContain("hidden");
      expect(document.getElementById("radio-filter-count").classList).toContain("hidden");
      expect(document.getElementById("radio-filter-trigger").classList).not.toContain("attestations-viewer__filter-dropdown-trigger--active");

      appStop(application);
    });

    it("filters items to the checked radio and updates the url", async () => {
      const application = await appStartRadio();

      setFilterRadioChecked("filter-radio-color-red", true);

      expect(document.getElementById("filter-radio-color-red").checked).toEqual(true);
      expect(document.getElementById("filter-radio-color-blue").checked).toEqual(false);
      expect(document.getElementById("ritem-1").classList).not.toContainEqual("hidden");
      expect(document.getElementById("ritem-2").classList).toContainEqual("hidden");
      expect(document.location.href).toEqual("http://localhost/?color=red#testing");
      expect(document.getElementById("radio-filter-clear").classList).not.toContain("hidden");
      expect(document.getElementById("radio-filter-count").classList).not.toContain("hidden");
      expect(document.getElementById("radio-filter-count").textContent).toEqual("1");
      expect(document.getElementById("radio-filter-trigger").classList).toContain("attestations-viewer__filter-dropdown-trigger--active");

      appStop(application);
    });

    it("switching the checked radio within the same group updates the filtered items", async () => {
      const application = await appStartRadio();

      setFilterRadioChecked("filter-radio-color-red", true);
      setFilterRadioChecked("filter-radio-color-red", false);
      setFilterRadioChecked("filter-radio-color-blue", true);

      expect(document.getElementById("filter-radio-color-red").checked).toEqual(false);
      expect(document.getElementById("filter-radio-color-blue").checked).toEqual(true);
      expect(document.getElementById("ritem-1").classList).toContainEqual("hidden");
      expect(document.getElementById("ritem-2").classList).not.toContainEqual("hidden");
      expect(document.location.href).toEqual("http://localhost/?color=blue#testing");

      appStop(application);
    });

    it("unchecks radios and shows all items after clearing", async () => {
      const application = await appStartRadio();

      setFilterRadioChecked("filter-radio-color-red", true);
      clearRadioFilters();

      expect(document.getElementById("filter-radio-color-red").checked).toEqual(false);
      expect(document.getElementById("filter-radio-color-blue").checked).toEqual(false);
      expect(document.getElementById("ritem-1").classList).not.toContainEqual("hidden");
      expect(document.getElementById("ritem-2").classList).not.toContainEqual("hidden");
      expect(document.location.href).toEqual("http://localhost/#testing");
      expect(document.getElementById("radio-filter-clear").classList).toContain("hidden");
      expect(document.getElementById("radio-filter-count").classList).toContain("hidden");
      expect(document.getElementById("radio-filter-trigger").classList).not.toContain("attestations-viewer__filter-dropdown-trigger--active");

      appStop(application);
    });
  });

  describe("with a sibling attestations-viewer controller", () => {
    const appStartViewer = async function () {
      const div = document.createElement("div");
      div.innerHTML = `
        <div id="viewer-controller" data-controller="attestations-viewer filter-list">
          <input id="viewer-filter-color-red" type="radio" name="color" value="red" data-action="filter-list#filter"
              data-filter-list-target="filter" data-filtered-source="color" data-comparison-type="exact">
          <input id="viewer-filter-color-blue" type="radio" name="color" value="blue" data-action="filter-list#filter"
              data-filter-list-target="filter" data-filtered-source="color" data-comparison-type="exact">
          <input id="viewer-filter-color-green" type="radio" name="color" value="green" data-action="filter-list#filter"
              data-filter-list-target="filter" data-filtered-source="color" data-comparison-type="exact">
          <ul>
            <li id="vitem-1" data-attestations-viewer-target="item" data-filter-list-target="item"
                data-filename="a" data-filtered-target-color='["red"]'>
              <button type="button" data-action="attestations-viewer#select" aria-pressed="true">a</button>
            </li>
            <li id="vitem-2" data-attestations-viewer-target="item" data-filter-list-target="item"
                data-filename="b" data-filtered-target-color='["blue"]'>
              <button type="button" data-action="attestations-viewer#select" aria-pressed="false">b</button>
            </li>
          </ul>
          <div>
            <div class="hidden" data-attestations-viewer-target="empty">No files match the current filters.</div>
            <div data-attestations-viewer-target="content" data-filename="a">Content A</div>
            <div class="hidden" data-attestations-viewer-target="content" data-filename="b">Content B</div>
          </div>
        </div>
        `;
      document.body.appendChild(div);

      const application = Application.start();
      application.register("filter-list", FilterListController);
      application.register("attestations-viewer", AttestationsViewerController);

      await delay(30);

      return application;
    };

    it("selects the first visible file once filtering hides the currently selected one", async () => {
      const application = await appStartViewer();

      document.getElementById("viewer-filter-color-blue").checked = true;
      document.getElementById("viewer-filter-color-blue").dispatchEvent(new Event("input"));
      await delay(10);

      expect(document.getElementById("vitem-1")).not.toHaveClass("attestations-viewer__file-item--is-selected");
      expect(document.getElementById("vitem-2")).toHaveClass("attestations-viewer__file-item--is-selected");
      expect(document.querySelector("[data-filename='a'][data-attestations-viewer-target='content']")).toHaveClass("hidden");
      expect(document.querySelector("[data-filename='b'][data-attestations-viewer-target='content']")).not.toHaveClass("hidden");

      appStop(application);
    });

    it("shows the empty state when no file matches the filters", async () => {
      const application = await appStartViewer();

      // Neither item is green, so this filter legitimately matches nothing.
      document.getElementById("viewer-filter-color-green").checked = true;
      document.getElementById("viewer-filter-color-green").dispatchEvent(new Event("input"));
      await delay(10);

      expect(document.getElementById("vitem-1")).toHaveClass("hidden");
      expect(document.getElementById("vitem-2")).toHaveClass("hidden");
      expect(document.querySelector("[data-attestations-viewer-target='empty']")).not.toHaveClass("hidden");
      expect(document.querySelector("[data-filename='a'][data-attestations-viewer-target='content']")).toHaveClass("hidden");
      expect(document.querySelector("[data-filename='b'][data-attestations-viewer-target='content']")).toHaveClass("hidden");

      appStop(application);
    });
  });

});
