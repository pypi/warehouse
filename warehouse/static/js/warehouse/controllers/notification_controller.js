/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import positionWarning from "../utils/position-warning";

export default class extends Controller {
  static targets = ["notification", "notificationDismiss"];

  /**
   * Get notification's id based on current DOM element id and version
   *
   * Notifications _without_ an element id and `notification-data-version`
   * will be treated as ephemeral: its dismissed state will not be persisted
   * into localStorage.
   *
   * @private
   */
  _getNotificationId() {
    /** Get data from `data-notification-version` attribute */
    if (this.notificationTarget.id) {
      const version = this.data.get("version") || "-1";
      return `${this.notificationTarget.id}_${version}__dismissed`;
    }
    return null;
  }

  initialize() {
    const notificationId = this._getNotificationId();
    const isDismissable = this.notificationTarget.classList.contains("notification-bar--dismissable");

    // Show the notification if:
    // - the notification is ephemeral, i.e. it has no notification ID
    // - it's not ephemeral and is not dismissable
    // - it's not ephemeral, is dismissable and the user has not dismissed it yet
    if (!notificationId || (isDismissable && !localStorage.getItem(notificationId))) {
      this.notificationTarget.classList.add("notification-bar--visible");
    }
  }

  dismiss() {
    const notificationId = this._getNotificationId();
    if (notificationId) {
      localStorage.setItem(notificationId, 1);
    }
    this.notificationTarget.classList.remove("notification-bar--visible");
    positionWarning();
  }
}
