/* SPDX-License-Identifier: Apache-2.0 */

import { gettext, ngettext } from "../utils/messages-access";

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

const convertToReadableText = (time) => {
  let { numDays, numMinutes, numHours } = time;

  if (numDays >= 1) {
    return ngettext("Yesterday", "About %1 days ago", numDays, numDays);
  }

  if (numHours > 0) {
    return ngettext("About an hour ago", "About %1 hours ago", numHours, numHours);
  } else if (numMinutes > 0) {
    return ngettext("About a minute ago", "About %1 minutes ago", numMinutes, numMinutes);
  } else {
    return gettext("Just now", "another");
  }
};

export default () => {
  const timeElements = document.querySelectorAll("time");
  for (const timeElement of timeElements) {
    const datetime = timeElement.getAttribute("datetime");
    const time = enumerateTime(datetime);
    if (time.isBeforeCutoff) {
      timeElement.innerText = convertToReadableText(time);
    }
  }
};
