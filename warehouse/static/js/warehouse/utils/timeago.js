const enumerateTime = (timestampString) => {
  var now = new Date(),
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
  var { numDays, numMinutes, numHours } = time;

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
  var timeElements = document.querySelectorAll("time");
  for (var timeElement of timeElements) {
    var datetime = timeElement.getAttribute("datetime");
    var time = enumerateTime(datetime);
    if (time.isBeforeCutoff) timeElement.innerText = convertToReadableText(time);
  }
};