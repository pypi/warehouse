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

/* global sinon, before, afterEach, describe, context, it, beforeEach */

import ViewportToggleController from "../../../warehouse/static/js/warehouse/controllers/viewport_toggle_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

chai.use(chaiDom);

describe("ViewportToggleController", function() {

  before(function() {
    registerApplication.call(this, "viewport-toggle", ViewportToggleController);
    this.sandbox = sinon.createSandbox();
  });

  beforeEach(function() {
    localStorage.removeItem("showDesktop");
    this.controller.switchToDesktopTarget.classList.add("hidden");
    this.controller.switchToMobileTarget.classList.add("hidden");
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("initial state", function() {
    context("with no `showDesktop` localStorage value", function() {
      it("shows the switch to desktop and hides switch to mobile", function() {
        this.controller.connect();

        // the CSS prevents the button from being shown
        expect(this.controller.switchToDesktopTarget).to.not.have.class("hidden");
        expect(this.controller.switchToMobileTarget).to.have.class("hidden");
      });
    });

    context("with `showDesktop` localStorage value", function() {
      it("shows the switch to desktop and hides switch to mobile", function() {
        localStorage.setItem("showDesktop", 1);

        this.controller.connect();

        expect(this.controller.switchToDesktopTarget).to.have.class("hidden");
        expect(this.controller.switchToMobileTarget).to.not.have.class("hidden");
        expect(document.getElementsByTagName("meta")["viewport"].content).to.equal("width=1280");
      });
    });
  });

  describe("clicking switch to desktop", function() {
    it("shows the switch to mobile button and sets localStorage", function() {
      this.controller.switchToDesktop();

      expect(this.controller.switchToDesktopTarget).to.have.class("hidden");
      expect(this.controller.switchToMobileTarget).to.not.have.class("hidden");
      expect(localStorage.getItem("showDesktop")).to.equal("1");
      expect(document.getElementsByTagName("meta")["viewport"].content).to.equal("width=1280");
    });
  });

  describe("clicking switch to mobile", function() {
    it("shows the switch to desktop button and removes localStorage", function() {
      this.controller.switchToMobile();

      expect(this.controller.switchToDesktopTarget).to.not.have.class("hidden");
      expect(this.controller.switchToMobileTarget).to.have.class("hidden");
      expect(localStorage.getItem("showDesktop")).to.be.null;
      expect(document.getElementsByTagName("meta")["viewport"].content).to.equal("width=device-width");
    });
  });

});
