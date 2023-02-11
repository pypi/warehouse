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
  static outlets = ["github-repo-info"];
  static values = { url: String };

  connect() {
    this.load();
  }

  load() {
    fetch(this.urlValue, {
      method: "GET",
      mode: "cors",
    })
      .then((response) => response.ok === true ? response.json() : null)
      .then((data) => {
        const stats = {
          bugs: data.open_issues_count,
          bugs_url: data.html_url + "/issues",
          followers: data.stargazers_count,
          followers_url: data.html_url + "/stargazers",
          forks: data.forks_count,
          forks_url: data.html_url + "/network/members",
        };
        this.githubRepoInfoOutlets.forEach(outlet => outlet.updateStats(stats));
      })
      // swallow errors, we don't want to show them to the user
      .catch(() => {});
  }
}
