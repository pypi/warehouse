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
