/* Licensed under the Apache License, Version 2.0 (the "License");
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

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import GitHubRepoInfoController from "../../warehouse/static/js/warehouse/controllers/github_repo_info_controller";

const startStimulus = () => {
  const application = Application.start();
  application.register("github-repo-info", GitHubRepoInfoController);
};

const mountDom = async () => {
  document.body.innerHTML = `
    <div id="github-repo-info"
          class="hidden"
          data-controller="github-repo-info"
          data-github-repo-info-url-value="https://api.github.com/repos/pypi/warehouse">
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
    </div>
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
        const el = document.getElementById("github-repo-info");
        expect(el).toHaveClass("hidden");
        expect(fetch.mock.calls.length).toEqual(1);
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
      })
    );

    startStimulus();
    mountDom();

    setTimeout(() => {
      try {
        const el = document.getElementById("github-repo-info");
        expect(el).not.toHaveClass("hidden");
        expect(fetch.mock.calls.length).toEqual(2);

        const stargazersCount = el.querySelector(
          "[data-github-repo-info-target='stargazersCount']"
        );
        const forksCount = el.querySelector(
          "[data-github-repo-info-target='forksCount']"
        );
        const openIssuesCount = el.querySelector(
          "[data-github-repo-info-target='openIssuesCount']"
        );

        expect(stargazersCount.textContent).toBe("100");
        expect(forksCount.textContent).toBe("200");
        expect(openIssuesCount.textContent).toBe("300");

        done();
      } catch (error) {
        done(error);
      }
    });
  });
});
