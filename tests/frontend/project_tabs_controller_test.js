/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import ProjectTabsController from "../../warehouse/static/js/warehouse/controllers/project_tabs_controller";


const tabsHTML = `
<div data-controller="project-tabs">
  <div class="tabs-container">
    <div class="vertical-tabs">
      <div class="vertical-tabs__tabs">
        <div class="sidebar-section">
          <h3 class="sidebar-section__title">Navigation</h3>
          <nav aria-label="Navigation for lunr">
            <ul class="vertical-tabs__list" role="tablist">
              <li role="tab">
                <a id="description-tab" href="#description" data-project-tabs-target="tab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--is-active" aria-selected="true" aria-label="Project description. Focus will be moved to the description.">
                  <i class="fa fa-align-left" aria-hidden="true"></i>
                  Project description
                </a>
              </li>
              <li role="tab">
                <a id="history-tab" href="#history" data-project-tabs-target="tab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon" aria-label="Release history. Focus will be moved to the history panel.">
                  <i class="fa fa-history" aria-hidden="true"></i>
                  Release history
                </a>
              </li>
              <li role="tab">
                <a id="data-tab" href="#files" data-project-tabs-target="tab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon" aria-label="Download files. Focus will be moved to the project files.">
                  <i class="fa fa-download" aria-hidden="true"></i>
                  Download files
                </a>
              </li>
            </ul>
          </nav>
        </div>
      </div>
      <div class="vertical-tabs__panel">
        <!-- mobile menu -->
        <nav aria-label="Navigation for project">
          <ul class="vertical-tabs__list" role="tablist">
            <li role="tab">
              <a id="mobile-description-tab" href="#description" data-project-tabs-target="mobileTab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--mobile vertical-tabs__tab--no-top-border vertical-tabs__tab--is-active" aria-selected="true" aria-label="Project description. Focus will be moved to the description.">
                <i class="fa fa-align-left" aria-hidden="true"></i>
                Project description
              </a>
            </li>
            <li role="tab">
              <a id="mobile-history-tab" href="#history" data-project-tabs-target="mobileTab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--mobile" aria-label="Release history. Focus will be moved to the history panel.">
              <i class="fa fa-history" aria-hidden="true"></i>
              Release history
            </a>
            <li role="tab">
              <a id="mobile-data-tab" href="#data" data-project-tabs-target="mobileTab" data-action="project-tabs#onTabClick" class="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--mobile" aria-label="Project details. Focus will be moved to the project details.">
                <i class="fa fa-info-circle" aria-hidden="true"></i>
                Project details
              </a>
            </li>
            </li>
          </ul>
        </nav>
        {# Tab: Project description #}
        <div id="description" data-project-tabs-target="content" class="vertical-tabs__content" role="tabpanel" aria-labelledby="description-tab mobile-description-tab" tabindex="-1">
          <h2 class="page-title">Project description</h2>
          <div class="project-description">Description</div>
        </div>

        {# Tab: project details #}
        <div id="data" data-project-tabs-target="content" class="vertical-tabs__content" role="tabpanel" aria-labelledby="mobile-data-tab" tabindex="-1">
          <h2 class="page-title">Project details</h2>
          <br>
        </div>

        {# Tab: Release history #}
        <div id="history" data-project-tabs-target="content" class="vertical-tabs__content" role="tabpanel" aria-labelledby="history-tab mobile-history-tab" tabindex="-1">
          <h2 class="page-title split-layout">
            <span>Release history</span>
            <a class="reset-text margin-top" href="#project-release-notifications">Release notifications</a>
          </h2>
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

      it("the first tab is shown", () => {
        const tab = document.getElementById("description-tab");
        expect(tab).toHaveClass("vertical-tabs__tab--is-active");
        expect(tab).toHaveAttribute("aria-selected");

        ["data", "history"].forEach(tabID => {
          expect(document.getElementById(tabID)).toHaveStyle("display: none");
          const tab = document.getElementById(`${tabID}-tab`);
          expect(tab).not.toHaveClass("vertical-tabs__tab--is-active");
        });
      });
    });

    describe("with hash in location", () => {
      beforeEach(() => {
        window.location.hash = "#history";
        document.body.innerHTML = tabsHTML;

        const application = Application.start();
        application.register("project-tabs", ProjectTabsController);
      });
      it("the matching tab is shown", () => {
        expect(document.getElementById("history")).toHaveStyle("display: block");
        const tab = document.getElementById("history-tab");
        expect(tab).toHaveClass("vertical-tabs__tab--is-active");
        expect(tab).toHaveAttribute("aria-selected");

        ["description", "data"].forEach(tabID => {
          expect(document.getElementById(tabID)).toHaveStyle("display: none");
          const tab = document.getElementById(`${tabID}-tab`);
          expect(tab).not.toHaveClass("vertical-tabs__tab--is-active");
          expect(tab).not.toHaveAttribute("aria-selected");
        });
      });
    });
  });

  describe("functionality", () => {
    beforeEach(() => {
      document.body.innerHTML = tabsHTML;

      const application = Application.start();
      application.register("project-tabs", ProjectTabsController);
    });

    describe("clicking in tabs", () => {
      it("hides other tabs and shows the matching one", () => {
        document.getElementById("history").click();

        expect(document.getElementById("history")).toHaveStyle("display: block");
        const tab = document.getElementById("history-tab");
        expect(tab).toHaveClass("vertical-tabs__tab--is-active");
        expect(tab).toHaveAttribute("aria-selected");

        ["description", "data"].forEach(tabID => {
          expect(document.getElementById(tabID)).toHaveStyle("display: none");
          const tab = document.getElementById(`${tabID}-tab`);
          expect(tab).not.toHaveClass("vertical-tabs__tab--is-active");
        });
      });
    });

    describe("changing the window hash", () => {
      it("hides other tabs and shows the matching one", () => {
        window.hash = "#history";

        expect(document.getElementById("history")).toHaveStyle("display: block");
        const tab = document.getElementById("history-tab");
        expect(tab).toHaveClass("vertical-tabs__tab--is-active");
        expect(tab).toHaveAttribute("aria-selected");

        ["description", "data"].forEach(tabID => {
          expect(document.getElementById(tabID)).toHaveStyle("display: none");
          const tab = document.getElementById(`${tabID}-tab`);
          expect(tab).not.toHaveClass("vertical-tabs__tab--is-active");
        });
      });
    });
  });
});
