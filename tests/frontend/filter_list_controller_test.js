/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it, jest */


import {Application} from "@hotwired/stimulus";
import FilterListController from "../../warehouse/static/js/warehouse/controllers/filter_list_controller";


const testFixtureHTMLVisibilityToggle = `
<p id="initial-toggle-visibility-shown" class="hidden initial-toggle-visibility">Initially hidden, should end up shown.</p>
<p id="initial-toggle-visibility-hidden" class="initial-toggle-visibility">Initially shown, should end up hidden.</p>
`;
const testFixtureHTMLShowing = `
<p id="shown-and-total" data-filter-list-target="summary"></p>
`;
const testFixtureHTMLFilters = `
<input id="filter-input" type="text" data-action="filter-list#filter" data-filter-list-target="filter" data-filtered-source="contentType" data-comparison-type="includes" data-auto-update-url-querystring="false">
<select id="filter-select"  data-action="filter-list#filter" data-filter-list-target="filter" data-filtered-source="myattr" data-comparison-type="exact" data-auto-update-url-querystring="true">
  <option selected value="">My Attrs</option>
  <option value="myattr1">myattr 1</option>
  <option value="myattr2">myattr 2</option>
  <option value="myattr3">myattr 3</option>
</select>
`;
const testFixtureHTMLItems = `
        <a id="url-update" href="https://example.com#testing" data-filter-list-target="url"></a>
        <a id="filter-clear" href="#" data-action="filter-list#filterClear">Show all files</a>
        <div id="item-1" class="my-item" data-filter-list-target="item" data-filtered-target-content-type='["contentType1","Content Type 1","contentType1a","Content Type 1a"]' data-filtered-target-myattr='["myattr1", "My Attr 1"]'>Item 1</div>
        <div id="item-2" class="my-item" data-filter-list-target="item" data-filtered-target-content-type='["contentType2","Content Type 2","contentType2a","Content Type 2a"]' data-filtered-target-myattr='["myattr2", "My Attr 2"]'>Item 2</div>
        <div id="item-3" class="my-item" data-filter-list-target="item" data-filtered-target-content-type='["contentType3","Content Type 3","contentType3a","Content Type 3a"]' data-filtered-target-myattr='["myattr3", "My Attr 3"]'>Item 3</div>
`;


describe("Filter list controller", () => {
  const setFilterSelectValue = function(value) {
    const elFilter = document.getElementById("filter-select");
    const dispatchEventSpy = jest.spyOn(elFilter, "dispatchEvent");

    elFilter.value = value;

    // Manually trigger the 'input' event to get the MutationObserver that Stimulus uses to be updated.
    // Also ensure the event has been dispatched.
    const event = new Event("change");
    elFilter.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
    return elFilter;
  };
  const setFilterInputValue = function(value) {
    const elFilter = document.getElementById("filter-input");
    const dispatchEventSpy = jest.spyOn(elFilter, "dispatchEvent");

    elFilter.value = value;

    // Manually trigger the 'input' event to get the MutationObserver that Stimulus uses to be updated.
    // Also ensure the event has been dispatched.
    const event = new Event("input");
    elFilter.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
  };
  const clearFilters = function() {
    const elUrl = document.getElementById("filter-clear");
    const dispatchEventSpy = jest.spyOn(elUrl, "dispatchEvent");
    const event = new Event("click");
    elUrl.dispatchEvent(event);
    expect(dispatchEventSpy).toHaveBeenCalledWith(event);
  };
  describe("is initialized as expected", () => {
    describe("makes expected elements visible", () => {
      let application;
      beforeEach(() => {
        document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLVisibilityToggle}
      </div>
      `;

        application = Application.start();
        application.register("filter-list", FilterListController);
      });
      afterEach(() => {
        document.body.innerHTML = "";
        application.stop();
      });

      it("toggles visibility", () => {
        const elShown = document.getElementById("initial-toggle-visibility-shown");
        expect(elShown.classList).not.toContain("hidden");

        const elHidden = document.getElementById("initial-toggle-visibility-hidden");
        expect(elHidden.classList).toContain("hidden");
      });
    });

    describe("finds filters and items", () => {
      let application;
      beforeEach(() => {
        document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;

        application = Application.start();
        application.register("filter-list", FilterListController);
      });
      afterEach(() => {
        document.body.innerHTML = "";
        application.stop();
      });


      it("has expected items and filters", () => {
        const elController = document.getElementById("controller");
        const controller = application.getControllerForElementAndIdentifier(elController, "filter-list");

        expect(controller.itemTargets).toHaveLength(3);
        expect(controller.itemTargets[0]).toHaveTextContent("Item 1");
        expect(controller.itemTargets[1]).toHaveTextContent("Item 2");
        expect(controller.itemTargets[2]).toHaveTextContent("Item 3");

        expect(controller.filterTargets).toHaveLength(2);
        expect(controller.filterTargets[0].id).toEqual("filter-input");
        expect(controller.filterTargets[1].id).toEqual("filter-select");

        expect(Object.keys(controller.mappingItemFilterData)).toHaveLength(3);
        expect(controller.mappingItemFilterData["0"]).toEqual({
          "contentType": ["contentType1","Content Type 1", "contentType1a", "Content Type 1a"],
          "myattr":["myattr1", "My Attr 1"],
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
      });
    });
  });

  describe("displays count of visible items", () => {
    let application;
    beforeEach(() => {
      document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLShowing}
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;

      application = Application.start();
      application.register("filter-list", FilterListController);
    });
    afterEach(() => {
      document.body.innerHTML = "";
      application.stop();
    });

    it("all items begin shown", () => {
      const elP = document.getElementById("shown-and-total");
      expect(elP.textContent).toEqual("Showing 3 of 3 files.");
      expect(document.getElementsByClassName("my-item").length).toEqual(3);

      const elUrl = document.getElementById("url-update");
      expect(elUrl.href).toEqual("https://example.com/#testing");
    });
    it("shows message when all items are hidden", () => {
      setFilterInputValue("lizards");

      const elItem1 = document.getElementById("item-1");
      expect(elItem1.classList).toContainEqual("hidden");

      const elItem2 = document.getElementById("item-2");
      expect(elItem2.classList).toContainEqual("hidden");

      const elItem3 = document.getElementById("item-3");
      expect(elItem3.classList).toContainEqual("hidden");

      const elP = document.getElementById("shown-and-total");
      expect(elP.textContent).toEqual("No files match the current filters. Showing 0 of 3 files.");
    });
  });


  describe("allows filtering", () => {

    describe("input text filters the items", () => {
      let application;
      beforeEach(() => {
        document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLShowing}
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;

        application = Application.start();
        application.register("filter-list", FilterListController);
      });
      afterEach(() => {
        document.body.innerHTML = "";
        application.stop();
      });

      it("the item classes are updated", () => {
        // Set select to no filter
        setFilterSelectValue("");

        setFilterInputValue("2");

        const elP = document.getElementById("url-update");
        expect(elP.textContent).toEqual("https://example.com/?contentType=2#testing");

        const elItem1 = document.getElementById("item-1");
        expect(elItem1.classList).toContainEqual("hidden");

        const elItem2 = document.getElementById("item-2");
        expect(elItem2.classList).not.toContainEqual("hidden");

        const elItem3 = document.getElementById("item-3");
        expect(elItem3.classList).toContainEqual("hidden");
      });
      it("shows all items after clearing the filters", () => {
        setFilterInputValue("lizards");

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
    });

    describe("selecting an option filters the items", () => {
      let application;
      beforeEach(() => {
        document.body.innerHTML = `
      <div id="controller" data-controller="filter-list">
        ${testFixtureHTMLFilters}
        ${testFixtureHTMLItems}
      </div>
      `;

        application = Application.start();
        application.register("filter-list", FilterListController);
      });
      afterEach(() => {
        document.body.innerHTML = "";
        application.stop();
      });

      it("the item classes are updated", () => {
        setFilterSelectValue("myattr3");

        const elItem1 = document.getElementById("item-1");
        expect(elItem1.classList).toContainEqual("hidden");

        const elItem2 = document.getElementById("item-2");
        expect(elItem2.classList).toContainEqual("hidden");

        const elItem3 = document.getElementById("item-3");
        expect(elItem3.classList).not.toContainEqual("hidden");

        const elP = document.getElementById("url-update");
        expect(elP.textContent).toEqual("https://example.com/?myattr=myattr3#testing");
      });
    });
  });
});
