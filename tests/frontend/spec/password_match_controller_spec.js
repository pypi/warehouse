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

/* global sinon, before, afterEach, describe, context, it */

import PasswordMatchController from "../../../warehouse/static/js/warehouse/controllers/password_match_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

chai.use(chaiDom);

describe("PasswordMatchController", function() {

  before(function() {
    registerApplication.call(this, "password-match", PasswordMatchController);
    this.sandbox = sinon.createSandbox();
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("initial state", function() {

    context("the password match message and submit button", function() {
      it("is hidden and enabled", function() {
        expect(this.controller.matchMessageTarget).to.have.class("hidden");
        expect(this.controller.submitTarget).to.have.attr("disabled", "");
      });
    });

  });

  describe("incorrect inputs", function() {

    context("adding text on one of the fields", function() {
      it("shows text warning of mismatch and disables submit", function() {
        // simulate typing password
        this.controller.passwordMatchTarget.value = "foo";
        this.controller.checkPasswordsMatch();

        expect(this.controller.matchMessageTarget).to.have.html("Passwords do not match");
        expect(this.controller.matchMessageTarget).to.not.have.class("hidden");
        expect(this.controller.matchMessageTarget).to.not.have.class("form-error--valid");
        expect(this.controller.submitTarget).to.have.attr("disabled", "");
      });
    });

    context("adding different text on each field", function() {
      it("shows text warning of mismatch and disables submit", function() {
        // simulate typing password
        this.controller.passwordMatchTargets[0].value = "foo";
        this.controller.passwordMatchTargets[1].value = "bar";
        this.controller.checkPasswordsMatch();

        expect(this.controller.matchMessageTarget).to.have.html("Passwords do not match");
        expect(this.controller.matchMessageTarget).to.not.have.class("hidden");
        expect(this.controller.matchMessageTarget).to.not.have.class("form-error--valid");
        expect(this.controller.submitTarget).to.have.attr("disabled", "");
      });
    });

  });

  describe("correct inputs", function() {

    context("adding the same text on each field", function() {
      it("shows success text and enables submit", function() {
        // simulate typing password
        this.controller.passwordMatchTargets[0].value = "foo";
        this.controller.passwordMatchTargets[1].value = "foo";
        this.controller.checkPasswordsMatch();

        expect(this.controller.matchMessageTarget).to.have.html("Passwords match");
        expect(this.controller.matchMessageTarget).to.not.have.class("hidden");
        expect(this.controller.matchMessageTarget).to.have.class("form-error--valid");
        expect(this.controller.submitTarget).to.not.have.attr("disabled");
      });
    });

  });

});
