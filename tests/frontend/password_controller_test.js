/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import PasswordController from "../../warehouse/static/js/warehouse/controllers/password_controller";

describe("Password controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="password">
    <label for="show-password">
      <input data-action="change->password#togglePasswords" data-password-target="showPassword" type="checkbox">&nbsp;Show password
    </label>
    <input id="password" data-password-target="password" placeholder="Your password" type="password" />
    <input id="confirm" data-password-target="password" placeholder="Confirm password" type="password" />
  </div>
    `;

    const application = Application.start();
    application.register("password", PasswordController);
  });

  describe("initial state", () => {
    describe("the show password checkbox", () => {
      it("is off", () => {
        const toggleCheckbox = document.getElementsByTagName("input")[0];
        expect(toggleCheckbox.getAttribute("checked")).toBeFalsy();
      });
    });
  });

  describe("functionality", function() {
    describe("clicking show password", function() {
      it("toggles password fields", function() {
        const passwordField = document.querySelector("#password");
        const confirmField = document.querySelector("#confirm");
        const toggleCheckbox = document.getElementsByTagName("input")[0];
        expect(passwordField).toHaveAttribute("type", "password");
        expect(confirmField).toHaveAttribute("type", "password");

        toggleCheckbox.click();

        expect(passwordField).toHaveAttribute("type", "text");
        expect(confirmField).toHaveAttribute("type", "text");

        toggleCheckbox.click();

        expect(passwordField).toHaveAttribute("type", "password");
        expect(confirmField).toHaveAttribute("type", "password");
      });
    });
  });
});
