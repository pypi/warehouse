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
import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [
    "forksCount",
    "forksUrl",
    "openIssuesCount",
    "openIssuesUrl",
    "stargazersCount",
    "stargazersUrl",
  ];
  static values = { url: String };

  // TODO: Why does this fire twice? Is it because of the position of CSI?
  connect() {
    this.load();
  }

  load() {
    fetch(this.urlValue, {
      method: "GET",
      mode: "cors",
    })
      .then((response) => response.json())
      .then((data) => {
        this.forksCountTarget.textContent = data.forks_count;
        this.forksUrlTarget.href = data.html_url + "/network/members";
        this.openIssuesCountTarget.textContent = data.open_issues_count;
        this.openIssuesUrlTarget.href = data.html_url + "/issues";
        this.stargazersCountTarget.textContent = data.stargazers_count;
        this.stargazersUrlTarget.href = data.html_url + "/stargazers";
        // unhide the container now that the data is populated
        this.element.classList.remove("hidden");
      })
      // swallow errors, we don't want to show them to the user
      .catch(() => {});
  }
}
