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

import { Application } from "stimulus";
import ViewportToggleController from "../../warehouse/static/js/warehouse/controllers/viewport_toggle_controller";


describe("Viewport toggle controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <div data-controller="viewport-toggle">
        <button id="switch-to-mobile" class="button button--primary button--switch-to-mobile hidden" data-target="viewport-toggle.switchToMobile" data-action="viewport-toggle#switchToMobile">
          Switch to mobile version
        </button>
        <div class="centered hide-on-desktop">
            <button id="switch-to-desktop" class="button button--switch-to-desktop hidden" data-target="viewport-toggle.switchToDesktop" data-action="viewport-toggle#switchToDesktop">
                Desktop version
            </button>
        </div>
    </div>
    `;
  });


  describe("initial state", function() {
    describe("with no `showDesktop` localStorage value", function() {
      beforeEach(() => {
        const application = Application.start();
        application.register("viewport-toggle", ViewportToggleController);
        // localStorage is empty
      });
      it("shows the switch to desktop and hides switch to mobile", function() {
        expect(document.getElementById("switch-to-desktop")).not.toHaveClass("hidden");
        expect(document.getElementById("switch-to-mobile")).toHaveClass("hidden");
      });
    });

    describe("with `showDesktop` localStorage value", function() {
      beforeEach(() => {
        const application = Application.start();
        application.register("viewport-toggle", ViewportToggleController);
        localStorage.setItem("showDesktop", 1);
        window.scrollTo = jest.fn();
      });

      it("shows the switch to desktop and hides switch to mobile", function() {
        expect(document.getElementById("switch-to-desktop")).toHaveClass("hidden");
        expect(document.getElementById("switch-to-mobile")).not.toHaveClass("hidden");
        expect(document.getElementsByTagName("meta")["viewport"].content).toEqual("width=1280");
      });
    });
  });

  describe("clicking switch to desktop", function() {
    beforeEach(() => {
      const application = Application.start();
      application.register("viewport-toggle", ViewportToggleController);
      window.scrollTo = jest.fn();
      // localStorage is empty
    });

    it("shows the switch to mobile button and sets localStorage", function() {
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
      const application = Application.start();
      application.register("viewport-toggle", ViewportToggleController);
      window.scrollTo = jest.fn();
      // localStorage is empty
    });
    it("shows the switch to desktop button and removes localStorage", function() {
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
