/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import ProjectTabsController from "../../warehouse/static/js/warehouse/controllers/project_tabs_controller";


const tabsHTML = `
<div data-controller="project-tabs">
  <div class="tabs-container">
    <div class="tabs">
      <div class="tabs__tabs">
        <div class="sidebar-section">
          <h3 class="sidebar-section__title">Navigation</h3>
          <nav aria-label="Navigation for lunr">
            <ul class="tabs__list" role="tablist">
              <li role="tab">
                <a id="description-tab" href="#description" data-project-tabs-target="tab" data-action="project-tabs#tabClick" class="tabs__tab tabs__tab--with-icon project-tabs__tab--is-active" aria-selected="true" aria-label="Project description. Focus will be moved to the description.">
                  <i class="fa fa-align-left" aria-hidden="true"></i>
                  Project description
                </a>
              </li>
              <li role="tab">
                <a id="history-tab" href="#history" data-project-tabs-target="tab" data-action="project-tabs#tabClick" class="tabs__tab tabs__tab--with-icon" aria-label="Release history. Focus will be moved to the history panel.">
                  <i class="fa fa-history" aria-hidden="true"></i>
                  Release history
                </a>
              </li>
              <li role="tab">
                <a id="files-tab" href="#files" data-project-tabs-target="tab" data-action="project-tabs#tabClick" class="tabs__tab tabs__tab--with-icon" aria-label="Download files. Focus will be moved to the project files.">
                  <i class="fa fa-download" aria-hidden="true"></i>
                  Download files
                </a>
              </li>
            </ul>
          </nav>
        </div>
      </div>
      <div class="tabs__panel">
        <!-- Tab: Project description -->
        <div id="description" data-project-tabs-target="content" role="tabpanel" aria-labelledby="description-tab" tabindex="-1">
          <h2 class="page-title">Project description</h2>
          <div class="project-description">Description</div>
        </div>

        <!-- Tab: Project details (no nav tab — mobile only, kept for hide/show coverage) -->
        <div id="data" data-project-tabs-target="content" role="tabpanel" tabindex="-1">
          <h2 class="page-title">Project details</h2>
        </div>

        <!-- Tab: Release history -->
        <div id="history" data-project-tabs-target="content" role="tabpanel" aria-labelledby="history-tab" tabindex="-1">
          <h2 class="page-title split-layout">
            <span>Release history</span>
            <a class="reset-text margin-top" href="#project-release-notifications">Release notifications</a>
          </h2>
        </div>

        <!-- Tab: Download files -->
        <div id="files" data-project-tabs-target="content" role="tabpanel" aria-labelledby="files-tab" tabindex="-1">
          <h2 class="page-title">Download files</h2>
          <div class="file">
            <div class="card file__card">
              <a href="/files/sample-1.0.tar.gz">sample-1.0.tar.gz</a>
              (1.0 KB
              <a href="#sample-1.0.tar.gz" data-project-tabs-target="tab" data-action="project-tabs#tabClick">view details</a>)
            </div>
          </div>
        </div>

        <!-- File details sub-panel (no nav tab, child of Download files) -->
        <div id="sample-1.0.tar.gz" data-project-tabs-target="content" role="tabpanel" tabindex="-1">
          <h2 class="page-title">File details</h2>
          <p>Details for the file sample-1.0.tar.gz.</p>
        </div>
      </div>
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
        expect(document.getElementById("description-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("history")).toHaveStyle("display: none");
        expect(document.getElementById("history-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("history-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("data")).toHaveStyle("display: none");
        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: none");
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
        expect(document.getElementById("history-tab")).toHaveAttribute("aria-selected");

        expect(document.getElementById("description")).toHaveStyle("display: none");
        expect(document.getElementById("description-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("description-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("data")).toHaveStyle("display: none");
        expect(document.getElementById("sample-1.0.tar.gz")).toHaveStyle("display: none");
      });
    });
  });

  describe("functionality", () => {
    let application;

    beforeEach(() => {
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
        expect(document.getElementById("description-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).not.toHaveAttribute("aria-selected");
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
        expect(document.getElementById("description-tab")).not.toHaveAttribute("aria-selected");
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
        expect(document.getElementById("files-tab")).not.toHaveAttribute("aria-selected");
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
        expect(document.getElementById("description-tab")).not.toHaveAttribute("aria-selected");

        expect(document.getElementById("files")).toHaveStyle("display: none");
        expect(document.getElementById("files-tab")).not.toHaveClass("project-tabs__tab--is-active");
        expect(document.getElementById("files-tab")).not.toHaveAttribute("aria-selected");
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
