/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [
    "forksCount",
    "forksUrl",
    "openIssuesCount",
    "openIssuesUrl",
    "openPRsCount",
    "openPRsUrl",
    "stargazersCount",
    "stargazersUrl",
  ];

  updateStats(stats) {
    this.forksCountTarget.textContent = stats.forks;
    this.forksUrlTarget.href = stats.forks_url;
    this.openIssuesCountTarget.textContent = stats.issues;
    this.openIssuesUrlTarget.href = stats.issues_url;
    this.openPRsCountTarget.textContent = stats.PRs;
    this.openPRsUrlTarget.href = stats.PRs_url;
    this.stargazersCountTarget.textContent = stats.followers;
    this.stargazersUrlTarget.href = stats.followers_url;

    // unhide the container now that the data is populated
    this.element.classList.remove("hidden");
  }
}
