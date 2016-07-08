const enumerateTime = (timestampString) => {
  var now = new Date(),
    timestamp = new Date(timestampString),
    diff = now - timestamp,
    time = {};

  time.seconds = diff / 1000;
  time.minutes = Math.floor(time.seconds / 60);
  time.hours = Math.floor(time.minutes / 60);
  time.days = Math.floor(time.hours / 24);
  time.isBeforeCutoff = time.days < 7;
  return time;
};

const convertToReadableText = (time) => {
  var { days, minutes, hours } = time;

  if (days >= 1) {
    return days == 1 ? "Yesterday." : `About ${days} days ago.`;
  }

  if (hours > 0) {
    var numHours = hours != 1 ? `${hours} hours` : "an hour";
    return `About ${numHours} ago.`;
  } else if (minutes > 0) {
    var numMinutes = minutes > 1 ? `${minutes} minutes` : "a minute";
    return `About ${numMinutes} ago.`;
  } else {
    return "Just Now.";
  }
};

export default (timeElements) => {
  for (var timeElement of timeElements) {
    var datetime = timeElement.getAttribute("datetime");
    var time = enumerateTime(datetime);
    if (time.isBeforeCutoff) timeElement.innerText = convertToReadableText(time);
  }
};