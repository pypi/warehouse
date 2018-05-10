import { Controller } from "stimulus";

const mockStatusResponse = {
  "page":{
    "id":"2p66nmmycsj3",
    "name":"Python Infrastructure",
    "url":"https://status.python.org",
    "updated_at": "2018-05-10T23:32:14Z"
  },
  "status": {
    "description": "Partial System Outage",
    "indicator": "major"
  }
};

const mockSummaryResponse = {
  "page": {
    "id": "2p66nmmycsj3",
    "name": "Python Infrastructure",
    "url": "https://status.python.org",
    "updated_at": "2018-05-10T23:32:14Z"
  },
  "status": {
    "description": "Partial System Outage",
    "indicator": "major"
  },
  "components": [
    {
      "created_at": "2014-05-03T01:22:07.274Z",
      "description": null,
      "id": "b13yz5g2cw10",
      "name": "API",
      "page_id": "2p66nmmycsj3",
      "position": 1,
      "status": "partial_outage",
      "updated_at": "2014-05-14T20:34:43.340Z"
    },
    {
      "created_at": "2014-05-03T01:22:07.286Z",
      "description": null,
      "id": "9397cnvk62zn",
      "name": "Management Portal",
      "page_id": "2p66nmmycsj3",
      "position": 2,
      "status": "major_outage",
      "updated_at": "2014-05-14T20:34:44.470Z"
    }
  ],
  "incidents": [
    {
      "created_at": "2014-05-14T14:22:39.441-06:00",
      "id": "cp306tmzcl0y",
      "impact": "critical",
      "incident_updates": [
        {
          "body": "Our master database has ham sandwiches flying out of the rack, and we're working our hardest to stop the bleeding. The whole site is down while we restore functionality, and we'll provide another update within 30 minutes.",
          "created_at": "2014-05-14T14:22:40.301-06:00",
          "display_at": "2014-05-14T14:22:40.301-06:00",
          "id": "jdy3tw5mt5r5",
          "incident_id": "cp306tmzcl0y",
          "status": "identified",
          "updated_at": "2014-05-14T14:22:40.301-06:00"
        }
      ],
      "monitoring_at": null,
      "name": "Unplanned Database Outage",
      "page_id": "2p66nmmycsj3",
      "resolved_at": null,
      "shortlink": "http://stspg.dev:5000/Q0E",
      "status": "identified",
      "updated_at": "2014-05-14T14:35:21.711-06:00"
    }
  ],
  "scheduled_maintenances": [
    {
      "created_at": "2014-05-14T14:24:40.430-06:00",
      "id": "w1zdr745wmfy",
      "impact": "none",
      "incident_updates": [
        {
          "body": "Our data center has informed us that they will be performing routine network maintenance. No interruption in service is expected. Any issues during this maintenance should be directed to our support center",
          "created_at": "2014-05-14T14:24:41.913-06:00",
          "display_at": "2014-05-14T14:24:41.913-06:00",
          "id": "qq0vx910b3qj",
          "incident_id": "w1zdr745wmfy",
          "status": "scheduled",
          "updated_at": "2014-05-14T14:24:41.913-06:00"
        }
      ],
      "monitoring_at": null,
      "name": "Network Maintenance (No Interruption Expected)",
      "page_id": "2p66nmmycsj3",
      "resolved_at": null,
      "scheduled_for": "2014-05-17T22:00:00.000-06:00",
      "scheduled_until": "2014-05-17T23:30:00.000-06:00",
      "shortlink": "http://stspg.dev:5000/Q0F",
      "status": "scheduled",
      "updated_at": "2014-05-14T14:24:41.918-06:00"
    },
    {
      "created_at": "2014-05-14T14:27:17.303-06:00",
      "id": "k7mf5z1gz05c",
      "impact": "minor",
      "incident_updates": [
        {
          "body": "Scheduled maintenance is currently in progress. We will provide updates as necessary.",
          "created_at": "2014-05-14T14:34:20.036-06:00",
          "display_at": "2014-05-14T14:34:20.036-06:00",
          "id": "drs62w8df6fs",
          "incident_id": "k7mf5z1gz05c",
          "status": "in_progress",
          "updated_at": "2014-05-14T14:34:20.036-06:00"
        },
        {
          "body": "We will be performing rolling upgrades to our web tier with a new kernel version so that Heartbleed will stop making us lose sleep at night. Increased load and latency is expected, but the app should still function appropriately. We will provide updates every 30 minutes with progress of the reboots.",
          "created_at": "2014-05-14T14:27:18.845-06:00",
          "display_at": "2014-05-14T14:27:18.845-06:00",
          "id": "z40y7398jqxc",
          "incident_id": "k7mf5z1gz05c",
          "status": "scheduled",
          "updated_at": "2014-05-14T14:27:18.845-06:00"
        }
      ],
      "monitoring_at": null,
      "name": "Web Tier Recycle",
      "page_id": "2p66nmmycsj3",
      "resolved_at": null,
      "scheduled_for": "2014-05-14T14:30:00.000-06:00",
      "scheduled_until": "2014-05-14T16:30:00.000-06:00",
      "shortlink": "http://stspg.dev:5000/Q0G",
      "status": "in_progress",
      "updated_at": "2014-05-14T14:35:12.258-06:00"
    }
  ]
};

const mockFetch = function(endpoint){
  if (endpoint.indexOf('status.json') !== -1) {
    return new Promise((resolve, reject) => resolve(mockStatusResponse));
  } else if (endpoint.indexOf('summary.json') !== -1) {
    return new Promise((resolve, reject) => resolve(mockSummaryResponse));
  }
};

export default class extends Controller {
  static targets = ["title", "components", "incidents"];
  incidentLimit = 3;
  statusPageDomain = null;
  // Enable mock data
  mock = true;

  jsUcfirst(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
  }

  _formatUtcDateTime(time) {
    const date = new Date(time);
    return `${date.getUTCFullYear()}-${date.getUTCMonth()}-${date.getUTCDate()} ${date.getUTCHours()}:${date.getUTCMinutes()}:${date.getUTCSeconds()} UTC`;
  }

  connect() {
    if (typeof window.fetch !== "undefined") {
      this.statusPageDomain = this.element.getAttribute("data-statuspage-domain");
      if (this.statusPageDomain === null) {
        return;
      }

      if (this.mock) {
        fetch = mockFetch;
      }

      fetch(`${this.statusPageDomain}/api/v2/status.json`).then((response) => {
        if (this.mock) {
          return response;
        }
        return response.json();
      }).then((json) => {
        const description = json.status.description;
        // If we get something other than "none", this is not normal.
        // if (json.status.indicator !== "none") {
          return json.status.indicator;
        // }
      }).then((indicator) => {
        fetch(`${this.statusPageDomain}/api/v2/summary.json`)
          .then((response) => {
            if (this.mock) {
              return response;
            }
            return response.json();
          })
          .then((json) => {
            // Iterate through components (assuming these are affected)
            let componentElement;
            let indicatorElement;
            let incidentElement;

            let numComponents = 0;
            for (let index in json.components) {
              if (numComponents >= this.incidentLimit) {
                break;
              }

              let component = json.components[index];

              indicatorElement = document.createElement("span");
              indicatorElement.classList.add(
                "notification-bar__status__component--indicator");
              indicatorElement.innerHTML = `${component.status}: `;

              componentElement = document.createElement("span");
              componentElement.classList.add(
                "notification-bar__status__component");
              componentElement.appendChild(indicatorElement);
              componentElement.innerHTML += `${component.name}`;
              componentElement.appendChild(document.createElement("br"));

              this.componentsTarget.appendChild(componentElement);

              numComponents += 1;
            }

            // Iterate through incidents
            let numIncidents = 0;
            if (json.incidents.length) {
              for (let index in json.incidents) {
                if (numIncidents >= this.incidentLimit) {
                  break;
                }

                let incident = json.incidents[index];

                indicatorElement = document.createElement("span");
                indicatorElement.classList.add(
                  "notification-bar__status__incident--indicator");
                indicatorElement.innerHTML = `${incident.impact}: `;

                incidentElement = document.createElement("span");
                incidentElement.classList.add(
                  "notification-bar__status__incident");
                incidentElement.appendChild(indicatorElement);
                incidentElement.innerHTML += `${incident.name}`;
                incidentElement.appendChild(document.createElement("br"));

                this.incidentsTarget.appendChild(incidentElement);
                numIncidents += 1;
              }
            }
          });
      });
    } else if (StatusPage) {
      // StatusPage javascript fallback?
      this.warehouseStatus = new StatusPage.page({
        page: "2p66nmmycsj3",
        component: "xt7f24hjvspn",
      });
    }
  }
}