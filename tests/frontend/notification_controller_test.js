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

/* global expect, beforeEach, describe, it */

import { Application } from "stimulus";
import NotificationController from "../../warehouse/static/js/warehouse/controllers/notification_controller";

const notificationContent = `
  <div id="notification" class="notification-bar notification-bar--danger notification-bar--dismissable" data-controller="notification" data-target="notification.notification">
    <span class="notification-bar__message">message</span>
    <button type="button" title="Dismiss this notification" data-target="notification.dismissButton" data-action="click->notification#dismiss" class="notification-bar__dismiss" aria-label="close"><i class="fa fa-times" aria-hidden="true"></i></button>
  </div>
`;

describe("Notification controller", () => {
  describe("standard notifications", () => {
    describe("initial state", () => {
      describe("when not previously dismissed", () => {
        beforeEach(() => {
          // Since the logic is in `connect` we need to setup and initialize
          // the Stimulus application just before the assertions
          document.body.innerHTML = notificationContent;
          const application = Application.start();
          application.register("notification", NotificationController);
        });
        it("are visible", () => {
          // the notification ID is not in localStorage
          const notification = document.getElementById("notification");
          expect(notification).toHaveClass("notification-bar--visible");
        });
      });

      describe("when previously dismissed", () => {
        beforeEach(() => {
          document.body.innerHTML = notificationContent;
          // Set the localStorage indicating it has been dismissed
          localStorage.setItem("notification_-1__dismissed", 1);
          const application = Application.start();
          application.register("notification", NotificationController);
        });
        it("are not visible", () => {
          const notification = document.getElementsByClassName("notification-bar")[0];
          expect(notification).not.toHaveClass("notification-bar--visible");
        });
      });
    });

    describe("once displayed", () => {
      beforeEach(() => {
        document.body.innerHTML = notificationContent;
        const application = Application.start();
        application.register("notification", NotificationController);
      });
      it("can be dismissed", () => {
        const notification = document.getElementsByClassName("notification-bar")[0];
        notification.querySelector("button").click();
        expect(notification).not.toHaveClass("notification-bar--visible");
      });
    });
  });

  describe("ephemeral notifications", () => {
    describe("initial state", () => {
      describe("when not previously dismissed", () => {
        beforeEach(() => {
          document.body.innerHTML = notificationContent;
          // ephemeral notifications do not have an `id` attribute
          const notification = document.getElementsByClassName("notification-bar")[0];
          notification.removeAttribute("id");
          const application = Application.start();
          application.register("notification", NotificationController);
        });
        it("are visible", () => {
          // the notification ID is not in localStorage
          const notification = document.getElementsByClassName("notification-bar")[0];
          expect(notification).toHaveClass("notification-bar--visible");
        });
      });

      describe("when previously dismissed", () => {
        beforeEach(() => {
          document.body.innerHTML = notificationContent;
          // ephemeral notifications do not have an `id` attribute
          const notification = document.getElementsByClassName("notification-bar")[0];
          notification.removeAttribute("id");
          // Set the localStorage indicating it has been dismissed
          localStorage.setItem("notification_-1__dismissed", 1);
          const application = Application.start();
          application.register("notification", NotificationController);
        });
        it("are visible regardless", () => {
          const notification = document.getElementsByClassName("notification-bar")[0];
          expect(notification).toHaveClass("notification-bar--visible");
        });
      });
    });

    describe("once displayed", () => {
      beforeEach(() => {
        document.body.innerHTML = notificationContent;
        // ephemeral notifications do not have an `id` attribute
        const notification = document.getElementsByClassName("notification-bar")[0];
        notification.removeAttribute("id");
        const application = Application.start();
        application.register("notification", NotificationController);
      });
      it("can be dismissed", () => {
        const notification = document.getElementsByClassName("notification-bar")[0];
        notification.querySelector("button").click();
        expect(notification).not.toHaveClass("notification-bar--visible");
      });
    });
  });
});