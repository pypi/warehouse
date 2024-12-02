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
  static values = {
    url: String,
    issueUrl: String,
  };

  connect() {
    this.load();
  }

  load() {
    const fetchParams = {
      method: "GET",
      mode: "cors",
    };
    const fetchRepoData = fetch(this.urlValue, fetchParams).then((response) =>
      response.ok === true ? response.json() : null,
    );

    const fetchIssueData = fetch(this.issueUrlValue, fetchParams).then(
      (response) => (response.ok === true ? response.json() : null),
    );

    const allData = Promise.all([fetchRepoData, fetchIssueData]);

    allData
      .then((res) => {
        const stats = {
          issues_url: res[0].html_url + "/issues",
          PRs_url: res[0].html_url + "/pulls",
          followers: res[0].stargazers_count,
          followers_url: res[0].html_url + "/stargazers",
          forks: res[0].forks_count,
          forks_url: res[0].html_url + "/network/members",
          issues: res[1].total_count,
          PRs: res[0].open_issues_count - res[1].total_count,
        };
        this.githubRepoInfoOutlets.forEach((outlet) =>
          outlet.updateStats(stats),
        );
      })
      // swallow errors, we don't want to show them to the user
      .catch(() => {});
  }
}
