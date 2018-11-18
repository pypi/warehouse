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
  connect() {
    let date = new Date(this.element.getAttribute("datetime"));
    let startOfDay = new Date();
    startOfDay.setUTCHours(0, 0, 0, 0);
    if (this.data.get("relative") == "true" && date > startOfDay) {
      this.element.innerHTML = distanceInWordsToNow(date, {includeSeconds: true}) + " ago";
    } else {
      const options = { month: "short", day: "numeric", year: "numeric" };
      this.element.innerHTML = date.toLocaleDateString("en-US", options); 
    }
  }
}

