/* global sinon, before, afterEach, describe, context, it, fixture */

import PasswordController from "../../../warehouse/static/js/warehouse/controllers/password_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

chai.use(chaiDom);

describe("PasswordController", function() {

  before(function() {
    registerApplication.call(this, "password", PasswordController);
    this.sandbox = sinon.createSandbox();
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("initial state", function() {
    context("the show password checkbox", function() {
      it("is off", function() {
        expect(this.controller.showPasswordTarget.checked).to.be.false;
      });
    });
  });

  describe("functionality", function() {
    context("clicking show password", function() {
      it("toggles password fields", function() {
        let passwordField = fixture.el.querySelector("#password");
        let confirmField = fixture.el.querySelector("#confirm");
        expect(passwordField).to.have.attr("type").equal("password");
        expect(confirmField).to.have.attr("type").equal("password");

        // simulate clicking on checkbox
        this.controller.showPasswordTarget.checked = true;
        this.controller.togglePasswords();

        expect(passwordField).to.have.attr("type").equal("text");
        expect(confirmField).to.have.attr("type").equal("text");

        // simulate clicking on checkbox
        this.controller.showPasswordTarget.checked = false;
        this.controller.togglePasswords();

        expect(passwordField).to.have.attr("type").equal("password");
        expect(confirmField).to.have.attr("type").equal("password");
      });
    });
  });
});
