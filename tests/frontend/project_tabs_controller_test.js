/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import ProjectTabsController from "../../warehouse/static/js/warehouse/controllers/project_tabs_controller";


const tabsHTML = `
<div data-controller="project-tabs">
  <nav class="project-tabs__tabs" aria-label="Navigation for lunr">
    <ul class="project-tabs__list" role="tablist">
      <li role="presentation">
        <a id="description-tab" href="#description" role="tab" data-project-tabs-target="tab" data-action="project-tabs#tabClick keydown->project-tabs#tabKeydown" class="project-tabs__tab project-tabs__tab--is-active" aria-selected="true" tabindex="0" aria-label="Project description. Focus will be moved to the description.">
          <span><i class="fa fa-align-left" aria-hidden="true"></i> Project description</span>
        </a>
      </li>
      <li role="presentation">
        <a id="history-tab" href="#history" role="tab" data-project-tabs-target="tab" data-action="project-tabs#tabClick keydown->project-tabs#tabKeydown" class="project-tabs__tab" aria-selected="false" tabindex="-1" aria-label="Release history. Focus will be moved to the history panel.">
          <span><i class="fa fa-history" aria-hidden="true"></i> Release history</span>
        </a>
      </li>
      <li role="presentation">
        <a id="files-tab" href="#files" role="tab" data-project-tabs-target="tab" data-action="project-tabs#tabClick keydown->project-tabs#tabKeydown" class="project-tabs__tab" aria-selected="false" tabindex="-1" aria-label="Download files. Focus will be moved to the project files.">
          <span><i class="fa fa-download" aria-hidden="true"></i> Download files</span>
        </a>
      </li>
    </ul>
  </nav>
  <div class="project-tabs__panel">
    <!-- Tab: Project description -->
    <div id="description" data-project-tabs-target="content" role="tabpanel" aria-labelledby="description-tab" tabindex="-1">
      <h2 class="page-title">Project description</h2>
      <div class="project-description">Description</div>
    </div>

    <!-- Tab: Project details (no nav tab — kept for hide/show coverage) -->
    <div id="data" data-project-tabs-target="content" role="tabpanel" tabindex="-1">
      <h2 class="page-title">Project details</h2>
    </div>

    <!-- Tab: Release history -->
    <div id="history" data-project-tabs-target="content" role="tabpanel" aria-labelledby="history-tab" tabindex="-1">
      <h2 class="page-title">Release history</h2>
    </div>

    <!-- Tab: Download files -->
    <div id="files" data-project-tabs-target="content" role="tabpanel" aria-labelledby="files-tab" tabindex="-1">
      <h2 class="page-title">Download files</h2>
      <div class="file">
        <div class="card file__card">
          <a href="/files/sample-1.0.tar.gz">sample-1.0.tar.gz</a>
          (1.0 KB
          <a href="#sample-1.0.tar.gz" data-project-tabs-target="tab" data-action="project-tabs#tabClick keydown->project-tabs#tabKeydown">view details</a>)
        </div>
      </div>
    </div>

    <!-- File details sub-panel (no nav tab, sibling of Download files) -->
    <div id="sample-1.0.tar.gz" data-project-tabs-target="content" role="tabpanel" tabindex="-1">
      <h2 class="page-title">File details</h2>
      <p>Details for the file sample-1.0.tar.gz.</p>
    </div>
  </div>
</div>
`;

describe("Project tabs controller", () => {

  describe("initial state", () => {
    describe("with no hash in location", () => {
      beforeEach(() => {
        document.body.innerHTML = tabsHTML;

        const application = Application.start();
        application.register("project-tabs", ProjectTabsController);
      });

      it("shows the first tab and hides all others", () => {
        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "true");
        expect(document.getElementById("description-tab")).toHaveAttribute("tabindex", "0");

        expect(document.getElementById("history")).toHaveStyle("display: none");
        expect(document.getElementById("history-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected", "false");
        expect(document.getElementById("history-tab")).toHaveAttribute("tabindex", "-1");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "false");
        expect(document.getElementById("files-tab")).toHaveAttribute("tabindex", "-1");

        expect(document.getElementById("data")).toHaveStyle("display: none");
        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: none");
      });
    });

    describe("with a file detail hash in location", () => {
      beforeEach(() => {
        window.location.hash = "#sample-1.0.tar.gz";
        document.body.innerHTML = tabsHTML;

        const application = Application.start();
        application.register("project-tabs", ProjectTabsController);
      });

      it("shows the file detail panel and keeps the files tab active", () => {
        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: block");
        expect(document.getElementById("files-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "true");
        expect(document.getElementById("files-tab")).toHaveAttribute("tabindex", "0");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("description")).toHaveStyle("display: none");
        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "false");
        expect(document.getElementById("description-tab")).toHaveAttribute("tabindex", "-1");
      });
    });

    describe("with hash in location", () => {
      beforeEach(() => {
        window.location.hash = "#history";
        document.body.innerHTML = tabsHTML;

        const application = Application.start();
        application.register("project-tabs", ProjectTabsController);
      });

      it("shows the matching tab and hides all others", () => {
        expect(document.getElementById("history")).toHaveStyle("display: block");
        expect(document.getElementById("history-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected", "true");
        expect(document.getElementById("history-tab")).toHaveAttribute("tabindex", "0");

        expect(document.getElementById("description")).toHaveStyle("display: none");
        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "false");
        expect(document.getElementById("description-tab")).toHaveAttribute("tabindex", "-1");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "false");
        expect(document.getElementById("files-tab")).toHaveAttribute("tabindex", "-1");

        expect(document.getElementById("data")).toHaveStyle("display: none");
        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: none");
      });
    });
  });

  describe("functionality", () => {
    let application;

    beforeEach(() => {
      window.location.hash = "";
      document.body.innerHTML = tabsHTML;

      application = Application.start();
      application.register("project-tabs", ProjectTabsController);
    });

    describe("clicking a tab", () => {
      it("shows the matching panel and hides all others", () => {
        document.getElementById("history-tab").click();

        expect(document.getElementById("history")).toHaveStyle("display: block");
        expect(document.getElementById("history-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("description")).toHaveStyle("display: none");
        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "false");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "false");
      });

      it("updates the URL hash", () => {
        const pushState = jest.spyOn(history, "pushState");
        document.getElementById("history-tab").click();
        expect(pushState).toHaveBeenCalledWith(null, "", "#history");
        pushState.mockRestore();
      });

      it("focuses the content panel", () => {
        const focus = jest.spyOn(HTMLElement.prototype, "focus");
        document.getElementById("history-tab").click();
        expect(focus).toHaveBeenCalledWith({ preventScroll: true });
        focus.mockRestore();
      });
    });

    describe("keyboard navigation", () => {
      it("ArrowRight moves to the next tab", () => {
        document.getElementById("description-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));

        expect(document.getElementById("history")).toHaveStyle("display: block");
        expect(document.getElementById("history-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected");
        expect(document.getElementById("description")).toHaveStyle("display: none");
      });

      it("ArrowLeft moves to the previous tab", () => {
        document.getElementById("history-tab").click();
        document.getElementById("history-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));

        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected");
      });

      it("ArrowRight wraps from last to first tab", () => {
        document.getElementById("files-tab").click();
        document.getElementById("files-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));

        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
      });

      it("ArrowLeft wraps from first to last tab", () => {
        document.getElementById("description-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));

        expect(document.getElementById("files")).toHaveStyle("display: block");
        expect(document.getElementById("files-tab")).toHaveClass("project-tabs__tab--is-active");
      });

      it("Home moves to the first tab", () => {
        document.getElementById("files-tab").click();
        document.getElementById("files-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));

        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
      });

      it("End moves to the last tab", () => {
        document.getElementById("description-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));

        expect(document.getElementById("files")).toHaveStyle("display: block");
        expect(document.getElementById("files-tab")).toHaveClass("project-tabs__tab--is-active");
      });

      it("ignores non-arrow keys", () => {
        document.getElementById("description-tab").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
      });
    });

    describe("viewing file details", () => {
      it("shows the file detail panel and keeps the files tab active", () => {
        document.getElementById("files-tab").click();
        document.querySelector("a[href='#sample-1.0.tar.gz']").click();

        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: block");
        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("description")).toHaveStyle("display: none");

        expect(document.getElementById("files-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "false");
      });

      it("focuses the file detail panel", () => {
        document.getElementById("files-tab").click();
        const focus = jest.spyOn(HTMLElement.prototype, "focus");
        document.querySelector("a[href='#sample-1.0.tar.gz']").click();
        expect(focus).toHaveBeenCalledWith({ preventScroll: true });
        focus.mockRestore();
      });

      it("is hidden when switching to another tab", () => {
        document.getElementById("files-tab").click();
        document.querySelector("a[href='#sample-1.0.tar.gz']").click();
        document.getElementById("history-tab").click();

        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: none");

        expect(document.getElementById("history")).toHaveStyle("display: block");
        expect(document.getElementById("history-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "false");
      });
    });

    describe("changing the window hash", () => {
      it("shows the matching panel and hides all others", () => {
        window.location.hash = "#history";
        window.dispatchEvent(new Event("hashchange"));

        expect(document.getElementById("history")).toHaveStyle("display: block");
        expect(document.getElementById("history-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("description")).toHaveStyle("display: none");
        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected", "false");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).toHaveAttribute("aria-selected", "false");
      });

      it("falls back to the first tab when the hash is cleared", () => {
        document.getElementById("history-tab").click();
        window.location.hash = "";
        window.dispatchEvent(new Event("hashchange"));

        expect(document.getElementById("description")).toHaveStyle("display: block");
        expect(document.getElementById("description-tab")).toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("history")).toHaveStyle("display: none");
        expect(document.getElementById("history-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected", "false");
      });
    });

    describe("disconnect", () => {
      it("removes the hashchange event listener", () => {
        const element = document.querySelector("[data-controller='project-tabs']");
        const controller = application.getControllerForElementAndIdentifier(element, "project-tabs");
        const removeEventListener = jest.spyOn(window, "removeEventListener");
        controller.disconnect();
        expect(removeEventListener).toHaveBeenCalledWith("hashchange", expect.any(Function));
        removeEventListener.mockRestore();
      });
    });
  });
});
