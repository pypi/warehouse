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
    return numDays == 1 ? "Yesterday." : `About ${numDays} days ago.`;
  }

  if (numHours > 0) {
    numHours = numHours != 1 ? `${numHours} hours` : "an hour";
    return `About ${numHours} ago.`;
  } else if (numMinutes > 0) {
    numMinutes = numMinutes > 1 ? `${numMinutes} minutes` : "a minute";
    return `About ${numMinutes} ago.`;
  } else {
    return "Just Now.";
  }
};

export default () => {
  const timeElements = document.querySelectorAll("time");
  for (const timeElement of timeElements) {
    const datetime = timeElement.getAttribute("datetime");
    const time = enumerateTime(datetime);
    if (time.isBeforeCutoff) timeElement.innerText = convertToReadableText(time);
  }
};
