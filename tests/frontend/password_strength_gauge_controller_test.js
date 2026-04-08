/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { getByPlaceholderText, fireEvent } from "@testing-library/dom";
import { Application } from "@hotwired/stimulus";
import PasswordStrengthGaugeController from "../../warehouse/static/js/warehouse/controllers/password_strength_gauge_controller";

const mockZxcvbn = jest.fn();

jest.mock("@zxcvbn-ts/core", () => ({
  zxcvbn: (...args) => mockZxcvbn(...args),
  zxcvbnOptions: { setOptions: jest.fn() },
}));
describe("Password strength gauge controller", () => {
  beforeEach(() => {
    mockZxcvbn.mockReset();

    document.body.innerHTML = `
  <div data-controller="password-strength-gauge">
    <input id="password" data-password-strength-gauge-target="password" placeholder="Your password" type="password" data-action="input->password-strength-gauge#checkPasswordStrength" />
    <p class="form-group__help-text">
      <strong>Password strength:</strong>
      <span class="password-strength">
        <span id="gauge" class="password-strength__gauge" data-password-strength-gauge-target="strengthGauge">
          <span class="sr-only">Password field is empty</span>
        </span>
      </span>
    </p>
  </div>
    `;

    const application = Application.start();
    application.register("password-strength-gauge", PasswordStrengthGaugeController);
  });

  describe("initial state", () => {
    describe("the password strength gauge and screen reader text", () => {
      it("are at 0 level and reading a password empty text", () => {
        const passwordTarget = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordTarget, { target: { value: "" } });

        const gauge = document.getElementById("gauge");
        const ZXCVBN_LEVELS = [0, 1, 2, 3, 4];
        ZXCVBN_LEVELS.forEach(i =>
          expect(gauge).not.toHaveClass(`password-strength__gauge--${i}`),
        );
        expect(gauge).not.toHaveAttribute("data-zxcvbn-score");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("Password field is empty");
      });
    });
  });

  describe("entering passwords", () => {
    describe("that are weak", () => {
      it("shows low score and suggestions on screen reader", async () => {
        mockZxcvbn.mockReturnValue({
          score: 0,
          feedback: {
            suggestions: ["test", "0", "level"],
          },
        });

        const passwordTarget = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordTarget, { target: { value: "foo" } });

        // Allow async checkPasswordStrength to resolve
        await new Promise((r) => setTimeout(r, 0));

        const gauge = document.getElementById("gauge");
        expect(gauge).toHaveClass("password-strength__gauge--0");
        expect(gauge).toHaveAttribute("data-zxcvbn-score", "0");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("test 0 level");
      });
    });

    describe("that are strong", () => {
      it("show high score and suggestions on screen reader", async () => {
        mockZxcvbn.mockReturnValue({
          score: 4,
          feedback: {
            suggestions: [],
          },
        });

        const passwordTarget = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordTarget, { target: { value: "the strongest password ever" } });

        // Allow async checkPasswordStrength to resolve
        await new Promise((r) => setTimeout(r, 0));

        const gauge = document.getElementById("gauge");
        expect(gauge).toHaveClass("password-strength__gauge--4");
        expect(gauge).toHaveAttribute("data-zxcvbn-score", "4");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("Password is strong");
      });
    });
  });
});
