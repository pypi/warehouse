/* SPDX-License-Identifier: Apache-2.0 */

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
