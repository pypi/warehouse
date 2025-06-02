/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [
    "forksCount",
    "forksUrl",
    "openIssuesCount",
    "openIssuesUrl",
    "starrersCount",
    "starrersUrl",
    "openMRsCount",
    "openMRsUrl",
  ];

  updateStats(stats) {
    this.forksCountTarget.textContent = stats.forks;
    this.forksUrlTarget.href = stats.forks_url;
    this.openIssuesCountTarget.textContent = stats.issues;
    this.openIssuesUrlTarget.href = stats.issues_url;
    this.openMRsCountTarget.textContent = stats.MRs;
    this.openMRsUrlTarget.href = stats.MRs_url;
    this.starrersCountTarget.textContent = stats.starrers;
    this.starrersUrlTarget.href = stats.starrers_url;

    // unhide the container now that the data is populated
    this.element.classList.remove("hidden");
  }
}
