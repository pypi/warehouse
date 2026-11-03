import { dateCell, remoteTable } from "./utils/remote_table";

const element = document.getElementById("project-activity-table");

if (element) {
  remoteTable(element, {
    placeholder: "No matching project activity",
    columns: [
      {
        title: "Event",
        field: "tag",
      },
      {
        title: "Time",
        field: "time",
        formatter: dateCell,
      },
      {
        title: "IP address",
        field: "ip_address",
      },
      {
        title: "Hashed IP address",
        field: "hashed_ip_address",
      },
      {
        title: "Location Info",
        field: "location_info",
      },
      {
        title: "User-Agent",
        field: "user_agent_info",
      },
      {
        title: "Additional information",
        field: "additional",
      },
    ],
  });
}