/* SPDX-License-Identifier: Apache-2.0 */

export default () => {
  if (typeof window.fetch !== "undefined") {
    const statusElement = document.querySelector("[data-statuspage-domain]");
    if (statusElement === null)
      return;
    const statusPageDomain = statusElement.getAttribute("data-statuspage-domain");
    fetch(`${statusPageDomain}/api/v2/status.json`).then((response) => {
      return response.json();
    }).then((json) => {
      statusElement.textContent = json.status.description;
    });
  }
};
