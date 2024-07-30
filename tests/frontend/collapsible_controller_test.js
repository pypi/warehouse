/* Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import CollapsibleController from "../../warehouse/static/js/warehouse/controllers/collapsible_controller";

describe("Collapsible controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <details id="element" class="callout-block" data-controller="collapsible" data-collapsible-identifier="project_roles" open>
    <summary id="collapse" class="callout-block__heading" data-action="click->collapsible#save">Project Roles</h3>
  </details>
    `;

    const application = Application.start();
    application.register("collapsible", CollapsibleController);
  });

  describe("no cookie is present", function() {
    it("the element is not collapsed", function() {
      const el = document.getElementById("element");
      expect(el).toHaveAttribute("open");
    });

    it("the element is collapsible", function() {
      const summary = document.getElementById("collapse");
      summary.click();

      const el = document.getElementById("element");
      expect(el).not.toHaveAttribute("open");

      setTimeout(function () {
        expect(document.cookie).toContain("callout_block_project_role_collapsed=1");
      }, 0);
    });
  });

  describe("cookie is present", function() {
    it("the element is collapsed", function() {
      document.cookie = "callout_block_settings_collapsed=1";
      const application = Application.start();
      application.register("collapsible", CollapsibleController);

      const el = document.getElementById("element");
      expect(el).toHaveAttribute("open");
    });
  });
});
