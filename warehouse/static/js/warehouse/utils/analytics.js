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

/* global dataLayer */

import * as cookie from "cookie";


export default () => {
  let element = document.querySelector("script[data-ga-id]");
  if (element) {
    // This is more or less taken straight from Google Analytics Control Panel
    window.dataLayer = window.dataLayer || [];
    var gtag = function(){ dataLayer.push(arguments); };

    gtag("js", new Date());
    gtag("config", element.dataset.gaId, { "anonymize_ip": true });

    // Determine if we have a user ID associated with this person, if so we'll
    // go ahead and tell Google it to enable better tracking of individual
    // users.
    let cookies = cookie.parse(document.cookie);
    if (cookies.user_id__insecure) {
      gtag("set", {"user_id": cookies.user_id__insecure});
    }
  }
};
