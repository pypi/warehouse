/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import ConfirmController from "../../warehouse/static/js/warehouse/controllers/confirm_controller";
import { fireEvent } from "@testing-library/dom";

describe("Confirm controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div class="modal" data-controller="confirm">
    <div class="modal__content" role="dialog">
      <div class="modal__body">
        <h3 class="modal__title">Delete package?</h3>
        <p>Confirm to continue.</p>
        <label for="package">Delete</label>
        <input id="input-target" name="package" data-action="input->confirm#check" data-confirm-target="input" type="text" autocomplete="off" autocorrect="off" autocapitalize="off">
        </div>
        <div class="modal__footer">
          <button id="button-target" data-confirm-target="button" data-expected="package" type="submit">
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

  describe("initial state", function () {
    describe("the button", function () {
      it("is disabled", function () {
        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });
  });

  describe("functionality", function () {
    describe("entering expected text", function () {
      it("enables the button", function () {
        fireEvent.input(document.getElementById("input-target"), {
          target: { value: "package" },
        });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).not.toHaveAttribute("disabled");
      });
    });

    describe("entering incorrect casing text", function () {
      it("enables the button", function () {
        fireEvent.input(document.getElementById("input-target"), {
          target: { value: "PACKAGE" },
        });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).not.toHaveAttribute("disabled");
      });
    });

    describe("entering incorrect text", function () {
      it("disables the button", function () {
        fireEvent.input(document.getElementById("input-target"), {
          target: { value: "foobar" },
        });

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });
  });
});

describe("Confirm controller with checkboxes and text input", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div class="modal" data-controller="confirm">
    <div class="modal__content" role="dialog">
      <div class="modal__body">
        <h3 class="modal__title">Delete package?</h3>
        <p>Confirm to continue.</p>
        <label for="package">Delete</label>
        <input id="input-target" name="package" data-action="input->confirm#check" data-confirm-target="input" type="text" autocomplete="off" autocorrect="off" autocapitalize="off">

        <input type="checkbox" data-action="input->confirm#check" data-confirm-target="checkbox" data-test="first-checkbox">
        <input type="checkbox" data-action="input->confirm#check" data-confirm-target="checkbox" data-test="second-checkbox">
        </div>
        <div class="modal__footer">
          <button id="button-target" data-confirm-target="button" data-expected="package" type="submit">
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

  it("should have action disabled by default", () => {
    const buttonTarget = document.getElementById("button-target");
    expect(buttonTarget).toHaveAttribute("disabled");
  });

  it("should have action disabled when checkboxes are not checked and input text check is satisfied", () => {
    fireEvent.input(document.getElementById("input-target"), {
      target: { value: "package" },
    });
    const buttonTarget = document.getElementById("button-target");
    // Button should be disabled still as the checkboxes have not been checked yet
    expect(buttonTarget).toHaveAttribute("disabled");
  });

  it("should have action disabled when checkboxes are checked and input text check is not satisfied", () => {
    fireEvent.input(document.querySelector("[data-test=first-checkbox]"), {
      target: { checked: true },
    });
    fireEvent.input(document.querySelector("[data-test=second-checkbox]"), {
      target: { checked: true },
    });
    const buttonTarget = document.getElementById("button-target");
    // Button should be disabled still as the input field doesn't have the correct text yet
    expect(buttonTarget).toHaveAttribute("disabled");
  });

  it("should have action disabled when only some of the checkboxes are checked", () => {
    fireEvent.input(document.getElementById("input-target"), {
      target: { value: "package" },
    });
    fireEvent.input(document.querySelector("[data-test=second-checkbox]"), {
      target: { checked: true },
    });
    const buttonTarget = document.getElementById("button-target");
    // Button should be disabled still as the input field doesn't have the correct text yet
    expect(buttonTarget).toHaveAttribute("disabled");
  });

  it("should have action enabled when both checkboxes are checked and input text checks are satisfied", () => {
    fireEvent.input(document.querySelector("[data-test=first-checkbox]"), {
      target: { checked: true },
    });
    fireEvent.input(document.querySelector("[data-test=second-checkbox]"), {
      target: { checked: true },
    });
    fireEvent.input(document.getElementById("input-target"), {
      target: { value: "package" },
    });
    const buttonTarget = document.getElementById("button-target");
    // Button should now be enabled -- both checkboxes are selected, and the input field has the correct text
    expect(buttonTarget).not.toHaveAttribute("disabled");
  });
});
