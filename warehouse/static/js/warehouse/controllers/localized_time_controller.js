/**
 * Licensed under the Apache License, Version 2.0 (the "License");
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
import { Controller } from "stimulus";
import distanceInWordsToNow from "date-fns/distance_in_words_to_now";

export default class extends Controller {

  getLocalTimeFromTimestamp(timestamp) {
    // Safari returns "Invalid Date" when passing timezone
    // it is assumed all timestamp attributes are UTC as modeled in the database
    let date = timestamp.substr(0, 10).split("-").map(i => parseInt(i));
    let time = timestamp.substr(11, 8).split(":").map(i => parseInt(i));
    return new Date(
      Date.UTC(parseInt(date[0]), parseInt(date[1]) - 1, parseInt(date[2]), ...time)
    );
  }

  connect() {
    const timestamp = this.element.getAttribute("datetime");
    let localTime = this.getLocalTimeFromTimestamp(timestamp);
    let startOfDay = new Date();
    startOfDay.setUTCHours(0, 0, 0, 0);
    if (this.data.get("relative") == "true" && localTime > startOfDay) {
      this.element.innerHTML = distanceInWordsToNow(localTime, {includeSeconds: true}) + " ago";
    } else {
      const options = { month: "short", day: "numeric", year: "numeric" };
      this.element.innerHTML = localTime.toLocaleDateString("en-US", options);
    }
  }
}
