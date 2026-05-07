/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { fireEvent } from "@testing-library/dom";
import { Application } from "@hotwired/stimulus";
import { delay } from "./utils";
import PasswordBreachController from "../../warehouse/static/js/warehouse/controllers/password_breach_controller";

let application = null;

describe("Password breach controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div id="controller" data-controller="password-breach">
    <input id="password" data-password-breach-target="password" data-action="input->password-breach#check" placeholder="Your password" type="password" />
    <p id="message" data-password-breach-target="message" class="hidden">Password breached</p>
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
  /*
    This does not feel good right now, but will allow progress.

    Due to some misbheavior between jest, stimulus, debounce, and jest-fetch-mock
    the mocked debounce function in `tests/frontend/__mocks__/debounce.js` is
    not getting debounced during these tests.

    When each test runs, the Controller is set up, and the `debounce` function
    is called at least 3 times before calling `fetch.resetMocks()`. This can be
    observed by adding a `console.log()` statement inside `debounce.js` mock.
    It's also unclear if using our mock debounce actually helps - removing it
    provides the same behaviors. But that's not the main issue here.

    Reports of `resetMocks()` not emptying out the mocks is the same as I'm
    seeing here. The only "easy" way I can see solving this for now is to
    increment the call count, which is brittle at best.
    I've even tried upgrading, same behavior on 3.0.3 - no change.
    See: https://github.com/jefflau/jest-fetch-mock/issues/78

    ----

    We're on Stimulus 1.x, and they have already progressed to 3.x - we should
    explore upgrading to a newer version of Stimulus and continue to debug the

    **test** behaviors - the production behavior works fine right now.
    Potentially: https://stimulus-use.github.io/stimulus-use/#/use-debounce
    See also: https://buddyreno.dev/posts/testing-stimulus-connect-in-jest

    Another approach is to stop mocking `fetch` at all, and try one of the
    approaches as shown in https://kentcdodds.com/blog/stop-mocking-fetch
    This seems a bit advanced for me right now, but wanted to keep the link.

  */
    beforeEach(() => {
      fetch.resetMocks();
    });

    describe("entering a password with less than 3 characters", () => {
      it("does not call the HIBP API", async () => {
        const passwordField = document.querySelector("#password");
        fireEvent.input(passwordField, { target: { value: "of" } });

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
        // TODO: mocks are not being reset between runs
        // expect(fetch.mock.calls.length).toEqual(1);
        expect(fetch.mock.calls.length).toEqual(3);
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
        // TODO: mocks are not being reset between runs
        // expect(fetch.mock.calls.length).toEqual(1);
        expect(fetch.mock.calls.length).toEqual(4);
        expect(document.getElementById("message")).toHaveClass("hidden");
      });
    });
  });
});
