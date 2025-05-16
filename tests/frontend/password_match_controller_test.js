/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { getByPlaceholderText, fireEvent } from "@testing-library/dom";
import { Application } from "@hotwired/stimulus";
import PasswordMatchController from "../../warehouse/static/js/warehouse/controllers/password_match_controller";

describe("Password match controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="password-match">
    <input id="password" data-password-match-target="passwordMatch" placeholder="Your password" type="password" data-action="input->password-match#checkPasswordsMatch" />
    <input id="confirm" data-password-match-target="passwordMatch" placeholder="Confirm password" type="password" data-action="input->password-match#checkPasswordsMatch" />
    <p data-password-match-target="matchMessage" class="hidden"></p>
    <input type="submit" data-password-match-target="submit">
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

  describe("incomplete inputs", function() {
    describe("adding text on only the first field", function() {
      it("disables submit", function() {
        const passwordMatch = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordMatch, { target: { value: "foo" } });

        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveClass("hidden");
        const submit = document.getElementsByTagName("input")[2];
        expect(submit).toHaveAttribute("disabled", "");
      });
    });

    describe("adding text on only the second field", function() {
      it("disables submit", function() {
        const confirmPasswordMatch = getByPlaceholderText(document.body, "Confirm password");
        fireEvent.input(confirmPasswordMatch, { target: { value: "foo" } });

        const message = document.getElementsByTagName("p")[0];
        expect(message).toHaveClass("hidden");
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
