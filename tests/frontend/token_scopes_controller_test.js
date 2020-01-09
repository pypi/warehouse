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

import { Application } from "stimulus";
import TokenScopesController from "../../warehouse/static/js/warehouse/controllers/token_scopes_controller";

describe("Confirm controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
    <div data-controller="token-scopes">
      <div>
        <input type="radio" name="token_scopes" value="scope:user" id="scope:user" data-action="token-scopes#user" checked>
        <label for="scope:user">Entire account (all projects)</label>
      </div>
      <div>
        <input type="radio" name="token_scopes" value="scope:by_project" id="scope:by_project" data-action="token-scopes#project" >
        <label for="scope:by_project">By project</label>
      </div>
      <div>
        <input type="checkbox" name="token_scopes" value="scope:project:lunr" id="scope:project:lunr" data-target="token-scopes.selector" disabled>
        <label for="scope:project:lunr" class="disabled" data-target="token-scopes.description">lunr</label>
      </div>
      <div>
        <input type="checkbox" name="token_scopes" value="scope:project:tailsocket" id="scope:project:tailsocket" data-target="token-scopes.selector" disabled>
        <label for="scope:project:tailsocket" class="disabled" data-target="token-scopes.description">tailsocket</label>
      </div>
    </div>
    `;

    const application = Application.start();
    application.register("token-scopes", TokenScopesController);
  });

  describe("clicking the radio button for by project", function() {
    it("enables the checkboxes and removes the `disabled` class from descriptions", function() {
      document.getElementById("scope:by_project").click();

      const checkboxes = document.querySelectorAll("input[type=\"checkbox\"]");
      checkboxes.forEach(cb => {
        expect(cb).not.toHaveAttribute("disabled");
        expect(cb.nextElementSibling).not.toHaveClass("disabled");
      });
    });
  });

  describe("clicking the radio button for user scope", function() {
    it("disables the checkboxes and adds the `disabled` class from descriptions", function() {
      document.getElementById("scope:by_project").click();
      document.getElementById("scope:user").click();

      const checkboxes = document.querySelectorAll("input[type=\"checkbox\"]");
      checkboxes.forEach(cb => {
        expect(cb).toHaveAttribute("disabled");
        expect(cb.nextElementSibling).toHaveClass("disabled");
      });
    });
  });
});
