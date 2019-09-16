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

import { getByPlaceholderText, fireEvent } from "@testing-library/dom";
import { Application } from "stimulus";
import PasswordMatchController from "../../warehouse/static/js/warehouse/controllers/password_match_controller";

describe("Password controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="password-match">
    <input id="password" data-target="password-match.passwordMatch" placeholder="Your password" type="password" data-action="input->password-match#checkPasswordsMatch" />
    <input id="confirm" data-target="password-match.passwordMatch" placeholder="Confirm password" type="password" data-action="input->password-match#checkPasswordsMatch" />
    <p data-target="password-match.matchMessage" class="hidden"></p>
    <input type="submit" data-target="password-match.submit">
  </div>
    `;

    const application = Application.start();
    application.register("password-match", PasswordMatchController);
  });

  describe("initial state", function() {
    describe("the password match message and submit button", function() {
      it("is hidden and enabled", function() {
        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveClass("hidden");
        const submit = document.getElementsByTagName("input")[2];
        expect(submit).toHaveAttribute("disabled", "");
      });
    });
  });

  describe("incorrect inputs", function() {
    describe("adding text on one of the fields", function() {
      it("shows text warning of mismatch and disables submit", function() {
        const passwordMatch = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordMatch, { target: { value: "foo" } });

        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveTextContent("Passwords do not match");
        expect(message).not.toHaveClass("hidden");
        expect(message).not.toHaveClass("form-error--valid");
        const submit = document.getElementsByTagName("input")[2];
        expect(submit).toHaveAttribute("disabled", "");
      });
    });

    describe("adding different text on each field", function() {
      it("shows text warning of mismatch and disables submit", function() {
        fireEvent.input(getByPlaceholderText(document.body, "Your password"), { target: { value: "foo" } });
        fireEvent.input(getByPlaceholderText(document.body, "Confirm password"), { target: { value: "bar" } });

        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveTextContent("Passwords do not match");
        expect(message).not.toHaveClass("hidden");
        expect(message).not.toHaveClass("form-error--valid");
        const submit = document.getElementsByTagName("input")[2];
        expect(submit).toHaveAttribute("disabled", "");
      });
    });
  });

  describe("correct inputs", function() {
    describe("adding the same text on each field", function() {
      it("shows success text and enables submit", function() {
        fireEvent.input(getByPlaceholderText(document.body, "Your password"), { target: { value: "foo" } });
        fireEvent.input(getByPlaceholderText(document.body, "Confirm password"), { target: { value: "foo" } });

        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveTextContent("Passwords match");
        expect(message).not.toHaveClass("hidden");
        expect(message).toHaveClass("form-error--valid");
        const submit = document.getElementsByTagName("input")[2];
        expect(submit).not.toHaveAttribute("disabled");
      });
    });

  });
});
