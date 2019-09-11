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
import PasswordController from "../../warehouse/static/js/warehouse/controllers/password_controller";

describe("Password controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="password">
    <label for="show-password">
      <input data-action="change->password#togglePasswords" data-target="password.showPassword" type="checkbox">&nbsp;Show password
    </label>
    <input id="password" data-target="password.password" placeholder="Your password" type="password" />
    <input id="confirm" data-target="password.password" placeholder="Confirm password" type="password" />
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