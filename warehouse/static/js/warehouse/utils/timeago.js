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

  if (numDays === 1) {
    return gettext("Yesterday");
  } else if (numDays > 1) {
    return ngettext("About %1 day ago", "About %1 days ago", numDays, numDays);
  }

  if (numHours === 1) {
    return gettext("About an hour ago");
  } else if (numHours > 1) {
    return ngettext("About %1 hour ago", "About %1 hours ago", numHours, numHours);
  }

  if (numMinutes === 1) {
    return gettext("About a minute ago");
  } else if (numMinutes > 1) {
    return ngettext("About %1 minute ago", "About %1 minutes ago", numMinutes, numMinutes);
  }

  return gettext("Just now");
};

export default () => {
  const timeElements = document.querySelectorAll("time");
  for (const timeElement of timeElements) {
    const datetime = timeElement.getAttribute("datetime");
    const time = enumerateTime(datetime);
    if (time.isBeforeCutoff) {
      timeElement.textContent = convertToReadableText(time);
    }
  }
};
