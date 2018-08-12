/* global sinon, before, afterEach, describe, context, it */

import PasswordStrengthGaugeController from "../../../warehouse/static/js/warehouse/controllers/password_strength_gauge_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

const ZXCVBN_LEVELS = [0, 1, 2, 3, 4];

chai.use(chaiDom);

describe("PasswordStrengthGaugeController", function() {

  before(function() {
    registerApplication.call(this, "password-strength-gauge", PasswordStrengthGaugeController);
    this.sandbox = sinon.createSandbox();
    window.zxcvbn = function() {};
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("initial state", function() {

    context("the password strength gauge and screen reader text", function() {
      it("are at 0 level and reading a password empty text", function() {
        ZXCVBN_LEVELS.forEach(i =>
          expect(this.controller.strengthGaugeTarget).to.not.have.class(`password-strength__gauge--${i}`)
        );
        expect(this.controller.strengthGaugeTarget).to.not.have.attr("data-zxcvbn-score");
        expect(this.controller.strengthGaugeTarget.querySelector(".sr-only")).to.have.html("Password field is empty");
      });
    });

  });

  describe("entering passwords", function() {

    context("that are weak", function() {
      it("show low score and suggestions on screen reader", function() {
        this.sandbox.stub(window, "zxcvbn").callsFake(() => {
          return {
            score: 0,
            feedback: {
              suggestions: ["test", "0", "level"],
            },
          };
        });
        // simulate typing password
        this.controller.passwordTarget.value = "foo";
        this.controller.checkPasswordStrength();

        expect(this.controller.strengthGaugeTarget).to.have.class("password-strength__gauge--0");
        expect(this.controller.strengthGaugeTarget).to.have.attr("data-zxcvbn-score", "0");
        expect(this.controller.strengthGaugeTarget.querySelector(".sr-only")).to.have.html("test 0 level");
      });
    });

    context("that are strong", function() {
      it("show high score and suggestions on screen reader", function() {
        this.sandbox.stub(window, "zxcvbn").callsFake(() => {
          return {
            score: 5,
            feedback: {
              suggestions: [],
            },
          };
        });
        // simulate typing password
        this.controller.passwordTarget.value = "the strongest password ever";
        this.controller.checkPasswordStrength();

        expect(this.controller.strengthGaugeTarget).to.have.class("password-strength__gauge--5");
        expect(this.controller.strengthGaugeTarget).to.have.attr("data-zxcvbn-score", "5");
        expect(this.controller.strengthGaugeTarget.querySelector(".sr-only")).to.have.html("Password is strong");
      });
    });

  });

});
