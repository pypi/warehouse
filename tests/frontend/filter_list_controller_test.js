/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, describe, it, jest */


import {Application} from "@hotwired/stimulus";
import FilterListController from "../../warehouse/static/js/warehouse/controllers/filter_list_controller";
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
const testFixtureHTMLItems = `
        <a id="url-update" href="https://example.com#testing" data-filter-list-target="url"></a>
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
    // console.log(`Start test ${expect.getState().currentTestName}`);
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
    document.body.innerHTML = "";
  };

  describe("is initialized as expected", () => {
    it("has expected items and filters", async () => {
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
      expect(elP.href).toEqual("https://example.com/#testing");

      appStop(application);
    });
  });

  describe("with sample application", () => {
    it("makes expected elements visible by toggling visibility", async () => {
      const application = await appStart();

      const elShown = document.getElementById("initial-toggle-visibility-shown");
      expect(elShown.classList).not.toContain("hidden");

      const elHidden = document.getElementById("initial-toggle-visibility-hidden");
      expect(elHidden.classList).toContain("hidden");

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
      expect(elUrl.href).toEqual("https://example.com/#testing");

      const elP = document.getElementById("shown-and-total");
      expect(document.getElementsByClassName("my-item").length).toEqual(3);
      expect(elP.textContent).toEqual("Showing 3 of 3 files.");

      appStop(application);
    });
    it("filter by input text updates the item classes", async () => {
      const application = await appStart();

      setFilterSelectValue("filter-select-myattr", "");
      setFilterSelectValue("filter-select-contentType", "");
      setFilterInputValue("filter-input-description", "2");

      const elP = document.getElementById("url-update");
      expect(elP.href).toEqual("https://example.com/#testing");

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

      setFilterInputValue("filter-input-description", "lizards");

      expectedSelectOptions("filter-select-myattr", [
        ["", true],
      ]);
      expectedSelectOptions("filter-select-contentType", [
        ["", true],
      ]);

      const elP1 = document.getElementById("shown-and-total");
      expect(elP1.textContent).toEqual("No files match the current filters. Showing 0 of 3 files.");

      const elUrl = document.getElementById("url-update");
      expect(elUrl.href).toEqual("https://example.com/#testing");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

      clearFilters();

      expect(elP1.textContent).toEqual("Showing 3 of 3 files.");

      expectedSelectOptions("filter-select-myattr", [
        ["", true], ["myattr1", false], ["myattr2", false], ["myattr3", false],
      ]);
      expectedSelectOptions("filter-select-contentType", [
        ["", true], ["contentType1", false], ["contentType2", false], ["contentType3", false],
      ]);

      const elP2 = document.getElementById("shown-and-total");
      expect(elP2.textContent).toEqual("Showing 3 of 3 files.");

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
      expect(elP.href).toEqual("https://example.com/?myattr=myattr3#testing");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).not.toContainEqual("hidden");

      appStop(application);
    });
  });

});
