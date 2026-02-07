/* SPDX-License-Identifier: Apache-2.0 */

const fetchOptions = {
  mode: "same-origin",
  credentials: "same-origin",
  cache: "default",
  redirect: "follow",
};

export default () => {
  // Check if we have an authenticated session
  let authed = document.cookie.split(";").some(
    v => v.trim().startsWith("user_id__insecure="),
  );

  // Each HTML include will generate a promise, which we'll later use to wait
  // on once all the promises have been resolved.
  let promises = [];

  // Fetch all of the elements with a data-html-include attribute and put them
  // into an array.
  let elements = Array.from(document.querySelectorAll("[data-html-include]"));

  // For each element we found, fetch whatever URL is pointed to by the
  // data-html-include attribute and replace it's content with that. This uses
  // the new fetch() API which returns a Promise.
  elements.forEach((element) => {
    let url = element.getAttribute("data-html-include");
    if (!authed) {
      // Don't fetch authed URLs if we aren't authenticated
      try {
        // Attempt to parse as full URL
        const pathname = new URL(url, "http://example.com").pathname;
        if (pathname.startsWith("/_includes/authed/")) {
          return;
        }
      } catch (e) {
        // If parsing fails, assume it's just a path
        if (url.startsWith("/_includes/authed/")) {
          return;
        }
      }
    }

    let p = fetch(url, fetchOptions)
      .then(response => {
        if (response.ok) { return response.text(); }
        else { return ""; }
      })
      .then(content => { element.innerHTML = content; });
    promises.push(p);
  });

  Promise.all(promises).then(() => {

    // Once all of our HTML includes have fired, then we'll go ahead and record
    // the fact that our HTML includes have happened. This allows us to
    // introspect the state of our includes inside of our Selenium tests.
    window._WarehouseHTMLIncluded = true;

    // Dispatch an event to any listeners that our CSI includes have loaded
    var event = new Event("CSILoaded");
    document.dispatchEvent(event);
  });
};
