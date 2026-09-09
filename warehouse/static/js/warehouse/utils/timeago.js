/* SPDX-License-Identifier: Apache-2.0 */

import { gettext, ngettext, hasTranslation } from "../utils/messages-access";

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

// pybabel only extracts string literals, so the message ids are repeated.
const convertToReadableText = (time) => {
  const { numDays, numMinutes, numHours } = time;

  if (numDays === 1) {
    return hasTranslation("Yesterday")
      ? gettext("Yesterday")
      : null;
  } else if (numDays > 1) {
    return hasTranslation("About %1 day ago")
      ? ngettext("About %1 day ago", "About %1 days ago", numDays, numDays)
      : null;
  }

  if (numHours === 1) {
    return hasTranslation("About an hour ago")
      ? gettext("About an hour ago")
      : null;
  } else if (numHours > 1) {
    return hasTranslation("About %1 hour ago")
      ? ngettext("About %1 hour ago", "About %1 hours ago", numHours, numHours)
      : null;
  }

  if (numMinutes === 1) {
    return hasTranslation("About a minute ago")
      ? gettext("About a minute ago")
      : null;
  } else if (numMinutes > 1) {
    return hasTranslation("About %1 minute ago")
      ? ngettext("About %1 minute ago", "About %1 minutes ago", numMinutes, numMinutes)
      : null;
  }

  return hasTranslation("Just now")
    ? gettext("Just now")
    : null;
};

export default () => {
  const timeElements = document.querySelectorAll("time");
  for (const timeElement of timeElements) {
    const datetime = timeElement.getAttribute("datetime");
    const time = enumerateTime(datetime);
    if (time.isBeforeCutoff) {
      const text = convertToReadableText(time);
      if (text !== null) {
        timeElement.textContent = text;
      }
    }
  }
};
