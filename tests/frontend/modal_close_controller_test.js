/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
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
        <input id="input-target" name="package" data-modal-close-target="input" type="text" autocomplete="off" autocorrect="off" autocapitalize="off">
        <div class="modal__footer">
          <button id="button-target" data-modal-close-target="button" type="submit">
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
