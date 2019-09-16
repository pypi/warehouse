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

/* global expect, beforeEach, describe, it, jest */

import { getByPlaceholderText, fireEvent } from "@testing-library/dom";
import { Application } from "stimulus";
import PasswordStrengthGaugeController from "../../warehouse/static/js/warehouse/controllers/password_strength_gauge_controller";

describe("Password strength gauge controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div data-controller="password-strength-gauge">
    <input id="password" data-target="password-strength-gauge.password" placeholder="Your password" type="password" data-action="input->password-strength-gauge#checkPasswordStrength" />
    <p class="form-group__help-text">
      <strong>Password strength:</strong>
      <span class="password-strength">
        <span id="gauge" class="password-strength__gauge" data-target="password-strength-gauge.strengthGauge">
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
        const gauge = document.getElementById("gauge");
        const ZXCVBN_LEVELS = [0, 1, 2, 3, 4];
        ZXCVBN_LEVELS.forEach(i =>
          expect(gauge).not.toHaveClass(`password-strength__gauge--${i}`)
        );
        expect(gauge).not.toHaveAttribute("data-zxcvbn-score");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("Password field is empty");
      });
    });
  });

  describe("entering passwords", () => {
    describe("that are weak", () => {
      it("shows low score and suggestions on screen reader", () => {
        window.zxcvbn = jest.fn(() => {
          return {
            score: 0,
            feedback: {
              suggestions: ["test", "0", "level"],
            },
          };
        });
        const passwordTarget = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordTarget, { target: { value: "foo" } });

        const gauge = document.getElementById("gauge");
        expect(gauge).toHaveClass("password-strength__gauge--0");
        expect(gauge).toHaveAttribute("data-zxcvbn-score", "0");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("test 0 level");
      });
    });

    describe("that are strong", () => {
      it("show high score and suggestions on screen reader", () => {
        window.zxcvbn = jest.fn(() => {
          return {
            score: 5,
            feedback: {
              suggestions: [],
            },
          };
        });
        const passwordTarget = getByPlaceholderText(document.body, "Your password");
        fireEvent.input(passwordTarget, { target: { value: "the strongest password ever" } });

        const gauge = document.getElementById("gauge");
        expect(gauge).toHaveClass("password-strength__gauge--5");
        expect(gauge).toHaveAttribute("data-zxcvbn-score", "5");
        expect(gauge.querySelector(".sr-only")).toHaveTextContent("Password is strong");
      });
    });
  });
});
