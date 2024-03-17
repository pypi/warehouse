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

import fetchGetText from "warehouse/utils/fetch-gettext";

const enumerateTime = (timestampString) => {
  const now = new Date(),
    timestamp = new Date(timestampString),
    timeDifference = now - timestamp,
    time = {};

  time.numMinutes = Math.floor((timeDifference / 1000) / 60);
  time.numHours = Math.floor(time.numMinutes / 60);
  time.numDays = Math.floor(time.numHours / 24);
  time.isBeforeCutoff = time.numDays < 7;
  return time;
};

const convertToReadableText = async (time) => {
  let { numDays, numMinutes, numHours } = time;

  if (numDays >= 1) {
    return fetchGetText("Yesterday", "About ${numDays} days ago", numDays, {"numDays": numDays});
  }

  if (numHours > 0) {
    return fetchGetText("an hour", "About ${numHours} ago", numHours, {"numHours": numHours});
  } else if (numMinutes > 0) {
    return fetchGetText("a minute", "About ${numMinutes} ago", numMinutes, {"numMinutes": numMinutes});
  } else {
    return fetchGetText("Just now");
  }
};

export default () => {
  const timeElements = document.querySelectorAll("time");
  for (const timeElement of timeElements) {
    const datetime = timeElement.getAttribute("datetime");
    const time = enumerateTime(datetime);
    if (time.isBeforeCutoff) {
      convertToReadableText(time)
        .then((text) => {
          timeElement.innerText = text.msg;
        });
    }
  }
};
