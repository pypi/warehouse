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
import ConfirmController from "../../warehouse/static/js/warehouse/controllers/confirm_controller";
import { fireEvent } from "@testing-library/dom";

describe("Confirm controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div class="modal" data-controller="confirm">
    <div class="modal__content" role="dialog">
        <a id="cancel" href="#modal-close" data-action="click->confirm#cancel" title="Close" class="modal__close">
            <i class="fa fa-times" aria-hidden="true"></i>
            <span class="sr-only">close</span>
        </a>
        <div class="modal__body">
            <h3 class="modal__title">Delete package?</h3>
        <p>Confirm to continue.</p>
        <label for="package">Delete</label>
        <input id="input-target" name="package" data-action="input->confirm#check" data-target="confirm.input" type="text" autocomplete="off" autocorrect="off" autocapitalize="off">
        </div>
        <div class="modal__footer">
            <button type="reset" data-action="click->confirm#cancel">Cancel</button>
            <button id="button-target" data-target="confirm.button" data-expected="package" type="submit">
                Confirm
            </button>
        </div>
        </form>
    </div>
  </div>
    `;

    const application = Application.start();
    application.register("confirm", ConfirmController);
  });

  describe("initial state", function() {
    describe("the button", function() {
      it("is disabled", function() {
        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });
  });

  describe("functionality", function() {
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

    describe("entering expected text", function() {
      it("enables the button", function() {
        fireEvent.input(document.getElementById("input-target"), { target: { value: "package" } });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).not.toHaveAttribute("disabled");
      });
    });

    describe("entering incorrect casing text", function() {
      it("enables the button", function() {
        fireEvent.input(document.getElementById("input-target"), { target: { value: "PACKAGE" } });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).not.toHaveAttribute("disabled");
      });
    });

    describe("entering incorrect text", function() {
      it("disables the button", function() {
        fireEvent.input(document.getElementById("input-target"), { target: { value: "foobar" } });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });
  });
});
