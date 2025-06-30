/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import formatDistanceToNow from "date-fns/formatDistanceToNow";
import format from "date-fns/format";

export default class extends Controller {

  getLocalTimeFromTimestamp(timestamp) {
    // Safari returns "Invalid Date" when passing timezone
    // it is assumed all timestamp attributes are UTC as modeled in the database
    let date = timestamp.substr(0, 10).split("-").map(i => parseInt(i));
    let time = timestamp.substr(11, 8).split(":").map(i => parseInt(i));
    return new Date(
      Date.UTC(parseInt(date[0]), parseInt(date[1]) - 1, parseInt(date[2]), ...time),
    );
  }

  connect() {
    const timestamp = this.element.getAttribute("datetime");
    const locale = document.documentElement.lang;
    let localTime = this.getLocalTimeFromTimestamp(timestamp);
    let isoDate = format(localTime, "yyyy-MM-dd HH:mm:ss (xxx)");
    let startOfDay = new Date();
    startOfDay.setUTCHours(0, 0, 0, 0);

    let isRelative = this.data.get("relative") === "true";
    let showTime = this.data.get("show-time") === "true";
    const options = { month: "short", day: "numeric", year: "numeric" };

    if (isRelative && localTime > startOfDay) {
      this.element.textContent = formatDistanceToNow(localTime, {includeSeconds: true}) + " ago";
    } else {
      if (showTime) {
        this.element.textContent = localTime.toLocaleTimeString(locale, options);
      } else {
        this.element.textContent = localTime.toLocaleDateString(locale, options);
      }
    }

    this.element.setAttribute("title", isoDate);
    this.element.setAttribute("aria-label", isoDate);
  }
}
