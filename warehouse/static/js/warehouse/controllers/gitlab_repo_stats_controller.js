/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static outlets = ["gitlab-repo-info"];
  static values = {
    repository: String,
  };

  connect() {
    this.load();
  }

  load() {
    const get_project_objects_count = (project_api_url, project_object, fetchParams) => {
      return fetch(
        `${project_api_url}/${project_object}?` + new URLSearchParams({
          "state": "opened",
          "per_page": 1,
        }),
        fetchParams,
      ).then((response) => {
        if(response.ok) {
          return response.json().then(
            (data) => Object.keys(data).length ? response.headers.get("X-Total-Pages") : 0,
          );
        }

        console.error(
          `Received ${response.status} HTTP code while fetching Gitlab ${project_object} data. The response is "${response.text}"`,
        );

        return 0;
      }).catch(error => {
        console.error(`An error ocured while fetching Gitlab ${project_object} data: ${error.message || error}`);
        return 0;
      });
    };

    const GITLAB_API_URL = "https://gitlab.com/api/v4";
    const project_id = encodeURIComponent(this.repositoryValue);
    const fetchParams = {
      method: "GET",
      mode: "cors",
    };

    const project_api_url = `${GITLAB_API_URL}/projects/${project_id}`;
    const project_info = fetch(
      project_api_url,
      fetchParams,
    ).then((response) =>
      response.ok === true ? response.json() : null,
    );

    const issues = get_project_objects_count(project_api_url, "issues", fetchParams);
    const merge_requests = get_project_objects_count(project_api_url, "merge_requests", fetchParams);

    Promise.all([project_info, issues, merge_requests]).then(
      ([project, issues_count, merge_requests_count]) => {
        const stats = {
          issues: issues_count,
          issues_url: project.web_url + "/-/issues",
          starrers: project.star_count || 0,
          starrers_url: project.web_url + "/-/starrers",
          forks: project.forks_count || 0,
          forks_url: project.web_url + "/-/forks",
          MRs: merge_requests_count,
          MRs_url: project.web_url + "/-/merge_requests",
        };
        this.gitlabRepoInfoOutlets.forEach((outlet) =>
          outlet.updateStats(stats),
        );
      })
      // swallow errors, we don't want to show them to the user
      .catch((error) => {
        console.error(`An error ocured while fetching Gitlab data: ${error.message || error}`);
      });
  }
}
