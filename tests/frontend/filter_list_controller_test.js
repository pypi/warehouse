/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it, jest */


import {Application} from "@hotwired/stimulus";
import FilterListController from "../../warehouse/static/js/warehouse/controllers/filter_list_controller";
import {delay} from "./utils";


const testFixtureHTMLVisibilityToggle = `
<p id="initial-toggle-visibility-shown" class="hidden initial-toggle-visibility">Initially hidden, should end up shown.</p>
<p id="initial-toggle-visibility-hidden" class="initial-toggle-visibility">Initially shown, should end up hidden.</p>
`;
const testFixtureHTMLShowing = `
<p id="shown-and-total" data-filter-list-target="summary"></p>
`;
const testFixtureHTMLFilters = `
<input id="filter-input-description" type="text" data-action="filter-list#filter" data-filter-list-target="filter" data-filtered-source="description" data-comparison-type="includes" data-auto-update-url-querystring="false">
<select id="filter-select-myattr" data-action="filter-list#filter" data-filter-list-target="filter" data-filtered-source="myattr" data-comparison-type="exact" data-auto-update-url-querystring="true">
  <option selected value="">My Attrs</option>
  <option value="myattr1">myattr 1</option>
  <option value="myattr2">myattr 2</option>
  <option value="myattr3">myattr 3</option>
</select>
<select id="filter-select-contentType" data-action="filter-list#filter" data-filter-list-target="filter" data-filtered-source="contentType" data-comparison-type="exact" data-auto-update-url-querystring="true">
  <option selected value="">Content Types</option>
  <option value="contentType1">Content Type 1</option>
  <option value="contentType2">Content Type 2</option>
  <option value="contentType3">Content Type 3</option>
</select>
`;
const testFixtureHTMLItems = `
        <a id="url-update" href="https://example.com#testing" data-filter-list-target="url"></a>
        <a id="filter-clear" href="#" data-action="filter-list#filterClear">Show all files</a>
        <div id="item-1" class="my-item" data-filter-list-target="item" data-filtered-target-description="Description 1" data-filtered-target-content-type='["contentType1","Content Type 1","contentType1a","Content Type 1a"]' data-filtered-target-myattr='["myattr1", "My Attr 1"]'>Item 1</div>
        <div id="item-2" class="my-item" data-filter-list-target="item" data-filtered-target-description="Description 2" data-filtered-target-content-type='["contentType2","Content Type 2","contentType2a","Content Type 2a"]' data-filtered-target-myattr='["myattr2", "My Attr 2"]'>Item 2</div>
        <div id="item-3" class="my-item" data-filter-list-target="item" data-filtered-target-description="Description 3" data-filtered-target-content-type='["contentType3","Content Type 3","contentType3a","Content Type 3a"]' data-filtered-target-myattr='["myattr3", "My Attr 3"]'>Item 3</div>
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
  const appStart = function () {
    console.log(`Start test ${expect.getState().currentTestName}`);
    document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLVisibilityToggle}
        ${testFixtureHTMLShowing}
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;

    const application = Application.start();
    application.register("filter-list", FilterListController);
    return application;
  };
  const appStop = function(application) {
    document.body.innerHTML = "";
    application.stop();
  };

  describe("is initialized as expected", () => {
    it("has expected items and filters", async () => {
      const application = appStart();

      // wait for app to be ready
      await delay(30);

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

      expect(Object.keys(controller.mappingItemFilterData)).toHaveLength(3);
      expect(controller.mappingItemFilterData["0"]).toEqual({
        "contentType": ["contentType1", "Content Type 1", "contentType1a", "Content Type 1a"],
        "myattr": ["myattr1", "My Attr 1"],
      });
      expect(controller.mappingItemFilterData["1"]).toEqual({
        "contentType": ["contentType2", "Content Type 2", "contentType2a", "Content Type 2a"],
        "myattr": ["myattr2", "My Attr 2"],
      });
      expect(controller.mappingItemFilterData["2"]).toEqual({
        "contentType": ["contentType3", "Content Type 3", "contentType3a", "Content Type 3a"],
        "myattr": ["myattr3", "My Attr 3"],
      });

      const elP = document.getElementById("url-update");
      expect(elP.textContent).toEqual("https://example.com/#testing");

      appStop(application);
    });
  });

  describe("with sample application", () => {
    beforeEach(() => {
      appStart();
    });

    afterEach(() => {
      document.body.innerHTML = "";
    });

    it("makes expected elements visible by toggling visibility", async () => {
      const elShown = document.getElementById("initial-toggle-visibility-shown");
      expect(elShown.classList).not.toContain("hidden");

      const elHidden = document.getElementById("initial-toggle-visibility-hidden");
      expect(elHidden.classList).toContain("hidden");
    });

    it("has expected count when all items begin shown", () => {
      const elP = document.getElementById("shown-and-total");
      expect(elP.textContent).toEqual("Showing 3 of 3 files.");
      expect(document.getElementsByClassName("my-item").length).toEqual(3);

      const elUrl = document.getElementById("url-update");
      expect(elUrl.href).toEqual("https://example.com/#testing");
    });
    it("has expected count when when all items are hidden", () => {
      setFilterInputValue("filter-input-description", "lizards");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

      const elP = document.getElementById("shown-and-total");
      expect(elP.textContent).toEqual("No files match the current filters. Showing 0 of 3 files.");
    });

    it("filter by input text updates the item classes", () => {
      setFilterSelectValue("filter-select-myattr", "");
      setFilterSelectValue("filter-select-contentType", "");
      setFilterInputValue("filter-input-description", "2");

      const elP = document.getElementById("url-update");
      expect(elP.textContent).toEqual("https://example.com/#testing");

      expect(document.getElementsByClassName("my-item").length).toEqual(3);
      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      console.log('check');
      expect(elItem2.classList).not.toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

    });
    it("shows all items after clearing the input text filter", () => {
      setFilterInputValue("filter-input-description", "lizards");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

      clearFilters();

      const elP = document.getElementById("shown-and-total");
      expect(elP.textContent).toEqual("Showing 3 of 3 files.");

      expect(elItem1.classList).not.toContainEqual("hidden");
      expect(elItem2.classList).not.toContainEqual("hidden");
      expect(elItem3.classList).not.toContainEqual("hidden");
    });

    it("selecting an option filters the items and updates the classes", async () => {
      setFilterSelectValue("filter-select-myattr", "myattr3");
      setFilterSelectValue("filter-select-contentType", "");
      setFilterInputValue("filter-input-description", "");

      const elP = document.getElementById("url-update");
      expect(elP.textContent).toEqual("https://example.com/?myattr=myattr3#testing");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      console.log('check');
      expect(elItem3.classList).not.toContainEqual("hidden");


      // Check that any dropdown filter that has a selection has all the options,
      // and any filter with no selection has reduced options matching the selections in other filters.
      const filterMyAttr = document.getElementById("filter-select-myattr");
      expect(filterMyAttr.options).toHaveLength(4);
      expect(filterMyAttr.options[0].value).toEqual("");
      expect(filterMyAttr.options[0].selected).toBeFalsy();
      expect(filterMyAttr.options[1].value).toEqual("myattr1");
      expect(filterMyAttr.options[1].selected).toBeFalsy();
      expect(filterMyAttr.options[2].value).toEqual("myattr2");
      expect(filterMyAttr.options[2].selected).toBeFalsy();
      expect(filterMyAttr.options[3].value).toEqual("myattr3");
      expect(filterMyAttr.options[3].selected).toBeTruthy();

      const filterContentType = document.getElementById("filter-select-contentType");
      expect(filterContentType.options).toHaveLength(2);
      expect(filterContentType.options[0].value).toEqual("");
      expect(filterContentType.options[0].selected).toBeTruthy();
      expect(filterContentType.options[1].value).toEqual("contentType3");
      expect(filterContentType.options[1].selected).toBeFalsy();
    });
  });
});
