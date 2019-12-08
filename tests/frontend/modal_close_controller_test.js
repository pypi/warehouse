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
import ModalCloseController from "../../warehouse/static/js/warehouse/controllers/modal_close_controller";

describe("Modal close controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div class="modal" data-controller="modal-close">
    <div class="modal__content" role="dialog">
      <a id="cancel" href="#modal-close" data-action="click->modal-close#cancel" title="Close" class="modal__close">
        <i class="fa fa-times" aria-hidden="true"></i>
        <span class="sr-only">close</span>
      </a>
      <div class="modal__body">
        <h3 class="modal__title">Modal Title</h3>
        <input id="input-target" name="package" data-target="modal-close.input" type="text" autocomplete="off" autocorrect="off" autocapitalize="off">
        <div class="modal__footer">
          <button id="button-target" data-target="modal-close.button" type="submit">
              Confirm
          </button>
        </div>
      </div>
    </div>
  </div>
    `;

    const application = Application.start();
    application.register("modal-close", ModalCloseController);
  });

  describe("clicking cancel", function() {
    it("sets the window location, resets the input target and disables the button", function() {
      document.getElementById("cancel").click();

      expect(window.location.href).toContain("#modal-close");
      const inputTarget = document.getElementById("input-target");
      expect(inputTarget.value).toEqual("");
      const buttonTarget = document.getElementById("button-target");
      expect(buttonTarget).toHaveAttribute("disabled");
    });
  });
});
