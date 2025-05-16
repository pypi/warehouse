/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import DeleteConfirmController from "../../warehouse/static/js/warehouse/controllers/delete_confirm_controller";
import { fireEvent } from "@testing-library/dom";

describe("DeleteConfirm controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="delete-confirm">
    <input id="input-one" type="checkbox" data-action="input->delete-confirm#check" data-delete-confirm-target="input">Something
    <input id="input-two" type="checkbox" data-action="input->delete-confirm#check" data-delete-confirm-target="input">Something else
    <a id="button-target" data-delete-confirm-target="button" disabled>Something</a>
  </div>
    `;

    const application = Application.start();
    application.register("delete-confirm", DeleteConfirmController);
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
    describe("checking one box", function() {
      it("doesnt enable the button", function() {
        const inputOne = document.getElementById("input-one");
        expect(inputOne).not.toBeChecked();
        fireEvent.click(inputOne);
        expect(inputOne).toBeChecked();

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });

    describe("checking both boxes", function() {
      it("enables the button", function() {
        const inputOne = document.getElementById("input-one");
        expect(inputOne).not.toBeChecked();
        fireEvent.click(inputOne);
        expect(inputOne).toBeChecked();

        const inputTwo = document.getElementById("input-two");
        expect(inputTwo).not.toBeChecked();
        fireEvent.click(inputTwo);
        expect(inputTwo).toBeChecked();

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).not.toHaveAttribute("disabled");
      });
    });

    describe("unchecking a box", function() {
      it("disables the button", function() {
        var inputOne = document.getElementById("input-one");
        expect(inputOne).not.toBeChecked();
        fireEvent.click(inputOne);
        expect(inputOne).toBeChecked();

        const inputTwo = document.getElementById("input-two");
        expect(inputTwo).not.toBeChecked();
        fireEvent.click(inputTwo);
        expect(inputTwo).toBeChecked();

        inputOne = document.getElementById("input-one");
        expect(inputOne).toBeChecked();
        fireEvent.click(inputOne);
        expect(inputOne).not.toBeChecked();

        const buttonTarget = document.getElementById("button-target");
        expect(buttonTarget).toHaveAttribute("disabled");
      });
    });
  });
});
