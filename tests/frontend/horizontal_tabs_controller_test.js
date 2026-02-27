/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import HorizontalTabsController from "../../warehouse/static/js/warehouse/controllers/horizontal_tabs_controller";

const tabsHTML = `
  <div class="horizontal-tabs" data-controller="horizontal-tabs" data-horizontal-tabs-index="0">
    <div class="horizontal-tabs__tabbar">
      <button data-horizontal-tabs-target="tab" data-action="horizontal-tabs#change" class="tab is-active">
        Publisher 1
      </button>
      <button data-horizontal-tabs-target="tab" data-action="horizontal-tabs#change" class="tab">
        Publisher 2
      </button>
      <button data-horizontal-tabs-target="tab" data-action="horizontal-tabs#change" class="tab">
        Publisher 3
      </button>
    </div>
    <div class="horizontal-tabs__tabcontent is-hidden" data-horizontal-tabs-target="tabPanel">
      <div>Publisher Form 1</div>
    </div>
    <div class="horizontal-tabs__tabcontent" data-horizontal-tabs-target="tabPanel">
      <div>Publisher Form 2</div>
    </div>
    <div class="horizontal-tabs__tabcontent" data-horizontal-tabs-target="tabPanel">
      <div>Publisher Form 3</div>
    </div>
  </div>
`;

describe("Horizontal tabs controller", () => {
  beforeEach(() => {
    document.body.innerHTML = tabsHTML;
    const application = Application.start();
    application.register("horizontal-tabs", HorizontalTabsController);
  });

  describe("on initialization", () => {
    it("the first tab is shown", () => {
      const tabs = document.querySelectorAll(".tab");
      const content = document.querySelectorAll(".horizontal-tabs__tabcontent");

      // First tab is shown
      expect(tabs[0]).toHaveClass("is-active");
      expect(content[0]).not.toHaveClass("is-hidden");

      // The other tabs are not shown
      expect(tabs[1]).not.toHaveClass("is-active");
      expect(content[1]).toHaveClass("is-hidden");
      expect(tabs[2]).not.toHaveClass("is-active");
      expect(content[2]).toHaveClass("is-hidden");
    });
  });

  describe("on change", () => {
    it("updates the active tab and panel when a tab is clicked", () => {
      const tabs = document.querySelectorAll(".tab");
      const content = document.querySelectorAll(".horizontal-tabs__tabcontent");

      // Click the second tab
      tabs[1].click();

      // First tab is not shown
      expect(tabs[0]).not.toHaveClass("is-active");
      expect(content[0]).toHaveClass("is-hidden");

      // Second tab is shown
      expect(tabs[1]).toHaveClass("is-active");
      expect(content[1]).not.toHaveClass("is-hidden");

      // Third tab is not shown
      expect(tabs[2]).not.toHaveClass("is-active");
      expect(content[2]).toHaveClass("is-hidden");
    });
  });

  describe("on initialization with errors", () => {
    beforeEach(() => {
      // Add some errors to the second tab
      const secondTabPanel = document.querySelectorAll(".horizontal-tabs__tabcontent")[1];
      secondTabPanel.innerHTML = "<div id='errors'></div>" + secondTabPanel.innerHTML;
      const application = Application.start();
      application.register("horizontal-tabs", HorizontalTabsController);
    });
    it("the tab with errors is shown", () => {
      const tabs = document.querySelectorAll(".tab");
      const content = document.querySelectorAll(".horizontal-tabs__tabcontent");

      // First tab is not shown
      expect(tabs[0]).not.toHaveClass("is-active");
      expect(content[0]).toHaveClass("is-hidden");

      // Second tab is shown
      expect(tabs[1]).toHaveClass("is-active");
      expect(content[1]).not.toHaveClass("is-hidden");

      // Third tab is not shown
      expect(tabs[2]).not.toHaveClass("is-active");
      expect(content[2]).toHaveClass("is-hidden");
    });
  });
});
