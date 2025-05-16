/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import format from "date-fns/format";
import { Application } from "@hotwired/stimulus";
import LocalizedTimeController from "../../warehouse/static/js/warehouse/controllers/localized_time_controller";

describe("Localized time controller", () => {
  describe("not relative and not showing time", () => {
    beforeEach(() => {
      // localized-time controller handles datetime in UTC only
      document.documentElement.lang = "en";
      document.body.innerHTML = `
      <time
        id="element"
        data-controller="localized-time"
        datetime="2019-09-20T19:06:58+0000"
        data-localized-time-relative="false"
        data-localized-time-show-time="false">
      </time>
      `;
      const application = Application.start();
      application.register("localized-time", LocalizedTimeController);
    });

    it("shows the local date", () => {
      const el = document.getElementById("element");
      expect(el).toHaveTextContent("Sep 20, 2019");
      // The expected ISO string in the title is localized
      const date = new Date(el.getAttribute("datetime"));
      const expectedDate = format(date, "yyyy-MM-dd HH:mm:ss (xxx)");
      expect(el).toHaveAttribute("title", expectedDate);
      expect(el).toHaveAttribute("aria-label", expectedDate);
      // Expect +00:00 because static tests run in UTC
      expect(expectedDate.endsWith("(+00:00)")).toBeTruthy();
    });
  });

  describe("relative and showing time", () => {
    beforeEach(() => {
      // localized-time controller handles datetime in UTC only
      const date = new Date();
      document.body.innerHTML = `
      <time
        id="element"
        data-controller="localized-time"
        datetime="${date.toISOString().slice(0, -1)}+0000"
        data-localized-time-relative="true"
        data-localized-time-show-time="true">
      </time>
      `;

      const application = Application.start();
      application.register("localized-time", LocalizedTimeController);
    });

    it("shows the local date", () => {
      const el = document.getElementById("element");
      expect(el).toHaveTextContent("less than 5 seconds ago");

      // There is a race condition between Stimulus connecting and the assertions
      // if the setup is not placed on the beforeEach causing the test to fail
      // To avoid this we add the date in the beforeEach and re-parse it here
      const date = new Date(el.getAttribute("datetime"));
      const expectedDate = format(date, "yyyy-MM-dd HH:mm:ss (xxx)");
      expect(el).toHaveAttribute("title", expectedDate);
      expect(el).toHaveAttribute("aria-label", expectedDate);
      // Expect +00:00 because static tests run in UTC
      expect(expectedDate.endsWith("(+00:00)")).toBeTruthy();
    });
  });
});
