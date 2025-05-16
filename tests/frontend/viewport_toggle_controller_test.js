/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import ViewportToggleController from "../../warehouse/static/js/warehouse/controllers/viewport_toggle_controller";


const viewportContent = `
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <div data-controller="viewport-toggle">
      <button id="switch-to-mobile" class="button button--primary button--switch-to-mobile hidden" data-viewport-toggle-target="switchToMobile" data-action="viewport-toggle#switchToMobile">
        Switch to mobile version
      </button>
      <div class="centered hide-on-desktop">
          <button id="switch-to-desktop" class="button button--switch-to-desktop hidden" data-viewport-toggle-target="switchToDesktop" data-action="viewport-toggle#switchToDesktop">
              Desktop version
          </button>
      </div>
  </div>
`;


function startStimulus() {
  // set the HTML before satarting the application, as the controller uses the
  // `connect()` function.
  document.body.innerHTML = viewportContent;
  const application = Application.start();
  application.register("viewport-toggle", ViewportToggleController);
}


describe("Viewport toggle controller", () => {

  describe("initial state", function() {
    describe("with no `showDesktop` localStorage value", function() {
      beforeEach(() => {
        localStorage.clear(); // localStorage is empty
        startStimulus();
      });
      it("shows the switch to desktop and hides switch to mobile", function() {
        expect(localStorage.getItem("showDesktop")).toBeNull;

        expect(document.getElementById("switch-to-desktop")).not.toHaveClass("hidden");
        expect(document.getElementById("switch-to-mobile")).toHaveClass("hidden");
      });
    });

    describe("with `showDesktop` localStorage value", function() {
      beforeEach(() => {
        localStorage.setItem("showDesktop", 1);
        window.scrollTo = jest.fn();
        startStimulus();
      });

      it("shows the switch to mobile and hides switch to desktop", function() {
        expect(localStorage.getItem("showDesktop")).toEqual("1");

        expect(document.getElementById("switch-to-desktop")).toHaveClass("hidden");
        expect(document.getElementById("switch-to-mobile")).not.toHaveClass("hidden");
        expect(document.getElementsByTagName("meta")["viewport"].content).toEqual("width=1280");
      });
    });
  });

  describe("clicking switch to desktop", function() {
    beforeEach(() => {
      localStorage.clear(); // localStorage is empty
      window.scrollTo = jest.fn();
      startStimulus();
    });

    it("shows the switch to mobile button and sets localStorage", function() {
      expect(localStorage.getItem("showDesktop")).toBeNull;

      const switchToDesktop = document.getElementById("switch-to-desktop");
      const switchToMobile = document.getElementById("switch-to-mobile");

      switchToDesktop.click();

      expect(switchToDesktop).toHaveClass("hidden");
      expect(switchToMobile).not.toHaveClass("hidden");
      expect(localStorage.getItem("showDesktop")).toEqual("1");
      expect(document.getElementsByTagName("meta")["viewport"].content).toEqual("width=1280");
    });
  });

  describe("clicking switch to mobile", function() {
    beforeEach(() => {
      localStorage.clear(); // localStorage is empty
      window.scrollTo = jest.fn();
      startStimulus();
    });
    it("shows the switch to desktop button and removes localStorage", function() {
      expect(localStorage.getItem("showDesktop")).toBeNull;

      const switchToDesktop = document.getElementById("switch-to-desktop");
      const switchToMobile = document.getElementById("switch-to-mobile");

      switchToMobile.click();

      expect(switchToDesktop).not.toHaveClass("hidden");
      expect(switchToMobile).toHaveClass("hidden");
      expect(localStorage.getItem("showDesktop")).toBeNull;
      expect(document.getElementsByTagName("meta")["viewport"].content).toEqual("width=device-width");
    });
  });
});
