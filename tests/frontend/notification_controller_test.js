/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import NotificationController from "../../warehouse/static/js/warehouse/controllers/notification_controller";

const notificationContent = `
  <div id="notification" class="notification-bar notification-bar--danger notification-bar--dismissable" data-controller="notification" data-notification-target="notification">
    <span class="notification-bar__message">message</span>
    <button type="button" title="Dismiss this notification" data-notification-target="dismissButton" data-action="click->notification#dismiss" class="notification-bar__dismiss" aria-label="close"><i class="fa fa-times" aria-hidden="true"></i></button>
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
