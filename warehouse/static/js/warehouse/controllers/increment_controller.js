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
import $ from "jquery";

export default class extends Controller {
  static targets = ["button"];

  constructor() {
    super();
    this.trending_projects_visible = 5;
    this.latest_releases_visible = 5;
  }
  addFiveTrending() {
    const trendingElements = document.getElementsByClassName(
      "hide-by-index-trending"
    );
    let j = this.trending_projects_visible;
    const end = (this.trending_projects_visible += 5);
    if (this.trending_projects_visible <= 20) {
      for (; j < end; j++) {
        if (trendingElements[j]) {
          trendingElements[j].style.display = "block";
        }
      }
      console.log(end);
      if (end === 20) {
        document.getElementById("increment-button-trending").style.display = "none";
      }
    }
  }
  addFiveLatest() {
    const latestElements = document.getElementsByClassName(
      "hide-by-index-latest"
    );
    let j = this.latest_releases_visible;
    const end = (this.latest_releases_visible += 5);
    if (this.latest_releases_visible <= 20) {
      for (; j < end; j++) {
        if (latestElements[j]) {
          latestElements[j].style.display = "block";
        }
      }
    }
    console.log(end);
    if (end === 20) {
      document.getElementById("increment-button-latest").style.display = "none";
    }
  }
}
