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

/* global ga */

import * as cookie from "cookie";


export default () => {
  // Here we want to ensure that our ga function exists in the global scope,
  // using the one that exists if it already does, or creating a new one that
  // just queues calls which will later be executed by Google's analytics.js
  window.ga = window.ga || function() {
    (ga.q = ga.q || []).push(arguments);
  };

  // Here we just set the current date for timing information.
  ga.l = new Date;

  // Now that we've ensured our ga object is setup, we'll get our script
  // element to pull the configuration out of it and parametrize the ga calls.
  let element = document.querySelector("script[data-ga-id]");
  if (element) {
    // Create the google tracker, ensuring that we tell Google to Anonymize our
    // user's IP addresses.
    ga("create", element.dataset.GaId, "auto", { anonymizeIp: true });

    // Determine if we have a user ID associated with this person, if so we'll
    // go ahead and tell Google it to enable better tracking of individual
    // users.
    let cookies = cookie.parse(document.cookie);
    if (cookies.user_id__insecure) {
      ga("set", "userId", cookies.user_id__insecure);
    }

    // Finally, we'll send an event to mark our page view.
    ga("send", "pageview");
  }
};
