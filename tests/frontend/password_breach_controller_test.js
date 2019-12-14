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

import { fireEvent } from "@testing-library/dom";
import { Application } from "stimulus";
import { delay } from "./utils";
import PasswordBreachController from "../../warehouse/static/js/warehouse/controllers/password_breach_controller";

let application = null;

describe("Password breach controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div id="controller" data-controller="password-breach">
    <input id="password" data-target="password-breach.password" data-action="input->password-breach#check" placeholder="Your password" type="password" />
    <p id="message" data-target="password-breach.message" class="hidden">Password breached</p>
  </div>
    `;

    application = Application.start();
    application.register("password-breach", PasswordBreachController);
  });

  describe("initial state", () => {
    describe("the message", () => {
      it("is hidden", () => {
        const message = document.getElementById("message");
        expect(message).toHaveClass("hidden");
      });
    });
  });

  describe("functionality", () => {
    beforeEach(() => {
      fetch.resetMocks();
    });

    describe("entering a password with less than 3 characters", () => {
      it("does not call the HIBP API", async () => {
        const passwordField = document.querySelector("#password");
        fireEvent.input(passwordField, { target: { value: "fo" } });

        await delay(25);  // arbitrary number of ms, too low may cause failures
        expect(fetch.mock.calls.length).toEqual(0);
      });
    });

    describe("entering a breached password with more than 2 characters", () => {
      it("calls the HIBP API and shows the message", async () => {
        // The response must match the slice of the hashed password
        fetch.mockResponse("7B5EA3F0FDBC95D0DD47F3C5BC275DA8A33:5270");
        const passwordField = document.querySelector("#password");
        fireEvent.input(passwordField, { target: { value: "foo" } });

        await delay(25);
        expect(fetch.mock.calls.length).toEqual(1);
        expect(document.getElementById("message")).not.toHaveClass("hidden");
      });
    });

    describe("entering a safe password with more than 2 characters", () => {
      it("calls the HIBP API and does not show the message", async () => {
        const verySecurePassword = "^woHw6w4j8zShVPyWtNKFn&DspydLQtIFPk97T@k$78H3pRsJ9RNB5SpLIux";
        // the response does not match the sliche of the hashed password
        fetch.mockResponse("00DC70F3D981248DF52C620198328108406:4");
        const passwordField = document.querySelector("#password");
        fireEvent.input(passwordField, { target: { value: verySecurePassword } });

        await delay(25);
        expect(fetch.mock.calls.length).toEqual(1);
        expect(document.getElementById("message")).toHaveClass("hidden");
      });
    });
  });
});
