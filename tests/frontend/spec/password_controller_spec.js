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
