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

import ConfirmController from "../../../warehouse/static/js/warehouse/controllers/confirm_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

chai.use(chaiDom);

describe("ConfirmController", function() {

  before(function() {
    registerApplication.call(this, "confirm", ConfirmController);
    this.sandbox = sinon.createSandbox();
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("initial state", function() {
    context("the button", function() {
      it("is disabled", function() {
        expect(this.controller.buttonTarget).to.have.attr("disabled");
      });
    });
  });

  describe("functionality", function() {
    context("clicking cancel", function() {
      it("sets the window location, resets the input target and disables the button", function() {
        this.controller.cancel();

        expect(window.location.href).to.include("#modal-close");
        expect(this.controller.inputTarget).to.have.value("");
        expect(this.controller.buttonTarget).to.have.attr("disabled");
      });
    });

    context("entering expected text", function() {
      it("enables the button", function() {
        this.controller.inputTarget.value = "package";
        this.controller.check();

        expect(this.controller.buttonTarget).to.not.have.attr("disabled");
      });
    });

    context("entering incorrect text", function() {
      it("disables the button", function() {
        this.controller.inputTarget.value = "foobar";
        this.controller.check();

        expect(this.controller.buttonTarget).to.have.attr("disabled");
      });
    });
  });
});
