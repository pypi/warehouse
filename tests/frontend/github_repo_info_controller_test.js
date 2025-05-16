/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import GitHubRepoInfoController from "../../warehouse/static/js/warehouse/controllers/github_repo_info_controller";
import GitHubRepoStatsController from "../../warehouse/static/js/warehouse/controllers/github_repo_stats_controller";

const startStimulus = () => {
  const application = Application.start();
  application.register("github-repo-info", GitHubRepoInfoController);
  application.register("github-repo-stats", GitHubRepoStatsController);
};

const mountDom = async () => {
  const gitHubRepoInfo = `
    <div class="hidden github-repo-info" data-controller="github-repo-info">
      <li>
        <a data-github-repo-info-target="stargazersUrl">
          <span data-github-repo-info-target="stargazersCount"></span>
        </a>
      </li>
      <li>
        <a data-github-repo-info-target="forksUrl">
          <span data-github-repo-info-target="forksCount"></span>
        </a>
      </li>
      <li>
        <a data-github-repo-info-target="openIssuesUrl">
          <span data-github-repo-info-target="openIssuesCount"></span>
        </a>
      </li>
      <li>
        <a data-github-repo-info-target="openPRsUrl">
          <span data-github-repo-info-target="openPRsCount"></span>
        </a>
      </li>
    </div>
  `;
  document.body.innerHTML = `
    <div id="github-repo-stats"
          data-controller="github-repo-stats"
          data-github-repo-stats-github-repo-info-outlet=".github-repo-info">
          data-github-repo-stats-url-value="https://api.github.com/repos/pypi/warehouse">
          data-github-repo-stats-issue-url-value="https://api.github.com/search/issues?q=repo:pypi/warehouse+type:issue+state:open&per_page=1">
    </div>
    <div id="sidebar">${gitHubRepoInfo}</div>
    <div id="tabs">${gitHubRepoInfo}</div>
  `;
};

describe("GitHub Repo Info controller", () => {
  beforeEach(() => {
    fetch.resetMocks();
  });

  it("invalid response hides", (done) => {
    fetch.mockResponse(null);

    startStimulus();
    mountDom();

    setTimeout(() => {
      try {
        const el = document.querySelector("#sidebar .github-repo-info");
        expect(el).toHaveClass("hidden");
        expect(fetch.mock.calls.length).toEqual(2);
        done();
      } catch (error) {
        done(error);
      }
    });
  });

  it("not-found response hides", (done) => {
    fetch.mockResponse(
      JSON.stringify({
        message: "Not Found",
        documentation_url: "https://docs.github.com/rest/reference/repos#get-a-repository",
      }),
      { status: 404 },
    );

    startStimulus();
    mountDom();

    setTimeout(() => {
      try {
        const el = document.querySelector("#sidebar .github-repo-info");
        expect(el).toHaveClass("hidden");
        expect(fetch.mock.calls.length).toEqual(4);
        done();
      } catch (error) {
        done(error);
      }
    });
  });

  it("valid response shows", (done) => {
    fetch.mockResponse(
      JSON.stringify({
        html_url: "https://github.com/pypi/warehouse",
        stargazers_count: 100,
        forks_count: 200,
        open_issues_count: 300,
        total_count: 50,
      }),
    );

    startStimulus();
    mountDom();

    setTimeout(() => {
      try {
        const el = document.querySelector("#sidebar .github-repo-info");
        expect(el).not.toHaveClass("hidden");
        expect(fetch.mock.calls.length).toEqual(6);

        const stargazersCount = el.querySelector(
          "[data-github-repo-info-target='stargazersCount']",
        );
        const forksCount = el.querySelector(
          "[data-github-repo-info-target='forksCount']",
        );
        const openIssuesCount = el.querySelector(
          "[data-github-repo-info-target='openIssuesCount']",
        );
        const openPRsCount = el.querySelector(
          "[data-github-repo-info-target='openPRsCount']",
        );

        expect(stargazersCount.textContent).toBe("100");
        expect(forksCount.textContent).toBe("200");
        expect(openIssuesCount.textContent).toBe("50");
        expect(openPRsCount.textContent).toBe("250");

        done();
      } catch (error) {
        done(error);
      }
    });
  });
});
