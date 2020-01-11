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

import format from "date-fns/format";
import { Application } from "stimulus";
import LocalizedTimeController from "../../warehouse/static/js/warehouse/controllers/localized_time_controller";

describe("Localized time controller", () => {
  describe("not relative and not showing time", () => {
    beforeEach(() => {
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
      const expectedDate = format(date, "YYYY-MM-DD HH:mm:ss");
      expect(el).toHaveAttribute("title", expectedDate);
      expect(el).toHaveAttribute("aria-label", expectedDate);
    });
  });

  describe("relative and showing time", () => {
    beforeEach(() => {
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
      const expectedDate = format(date, "YYYY-MM-DD HH:mm:ss");
      expect(el).toHaveAttribute("title", expectedDate);
      expect(el).toHaveAttribute("aria-label", expectedDate);
    });
  });
});
