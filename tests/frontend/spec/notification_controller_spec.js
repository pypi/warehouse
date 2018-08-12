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

import NotificationController from "../../../warehouse/static/js/warehouse/controllers/notification_controller";
import { registerApplication } from "./helpers";
import chai, { expect } from "chai";
import chaiDom from "chai-dom";

chai.use(chaiDom);


describe("NotificationController", function() {

  before(function() {
    registerApplication.call(this, "notification", NotificationController);
    this.sandbox = sinon.createSandbox();
  });

  beforeEach(function() {
    // the initial state of notifications is not visible
    this.controller.notificationTarget.classList.remove("notification-bar--visible");
  });

  afterEach(function() {
    this.sandbox.restore();
  });

  describe("standard notifications", function() {

    before(function() {
      // standard notifications have an ID
      this.controller.element.id = "notification-id";
    });

    context("initial state", function() {
      context("when not present in localStorage", function() {
        it("are visible", function() {
          localStorage.removeItem(this.controller._getNotificationId());
          this.controller.initialize();
          expect(this.controller.notificationTarget).to.have.class("notification-bar--visible");
        });
      });

      context("when present in localStorage", function() {
        it("are not visible", function() {
          localStorage.setItem(this.controller._getNotificationId(), 1);
          this.controller.initialize();
          expect(this.controller.notificationTarget).to.not.have.class("notification-bar--visible");
        });
      });
    });

    it("can be dismissed", function() {
      this.controller.dismiss();
      expect(this.controller.notificationTarget).to.not.have.class("notification-bar--visible");
    });
  });

  describe("ephemeral notifications", function() {

    before(function() {
      // ephemeral notifications have no ID
      this.controller.element.removeAttribute("id");
    });

    context("initial state", function() {
      context("when not present in localStorage", function() {
        it("are visible", function() {
          localStorage.removeItem(this.controller._getNotificationId());
          this.controller.initialize();
          expect(this.controller.notificationTarget).to.have.class("notification-bar--visible");
        });
      });

      context("when present in localStorage", function() {
        it("are not visible", function() {
          localStorage.setItem(this.controller._getNotificationId(), 1);
          this.controller.initialize();
          expect(this.controller.notificationTarget).to.have.class("notification-bar--visible");
        });
      });
    });

    it("can be dismissed", function() {
      this.controller.dismiss();
      expect(this.controller.notificationTarget).to.not.have.class("notification-bar--visible");
    });

  });

});
