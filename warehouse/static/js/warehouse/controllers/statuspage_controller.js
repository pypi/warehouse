import { Controller } from "stimulus";

const MockStatusPage = {
  scheduled_maintenances: function (options) {
    if (options.success) options.success();
  },
  incidents: function (options) {
    if (options.success) options.success();
  },
};

const mockIncidentResponse = {
  "page": {
    "id": "2p66nmmycsj3",
    "name": "Python Infrastructure",
    "url": "https://status.python.org",
    "updated_at": "2018-04-27T05:29:29Z",
  },
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
          "updated_at": "2014-05-14T14:22:40.301-06:00",
        },
      ],
      "monitoring_at": null,
      "name": "Unplanned Database Outage",
      "page_id": "2p66nmmycsj3",
      "resolved_at": null,
      "shortlink": "http://stspg.dev:5000/Q0E",
      "status": "identified",
      "updated_at": "2014-05-14T14:35:21.711-06:00",
    },
  ],
};

export default class extends Controller {
  static targets = ["title", "events"];

  mock = true;

  unhide(elementId) {
    var x = document.getElementById(elementId);
    if (x.style.display === "none") {
      x.style.display = "block";
    }
  }

  jsUcfirst(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
  }

  _getIncidents() {
    const _this = this;
    this.warehouseStatus.incidents({
      // filter: "unresolved",
      success: function (data) {
        if (_this.mock) {
          let data = mockIncidentResponse;
        }
        for (let index in data.incidents) {
          if (index >= 10) break;
          _this._addIncident("active-incidents", data.incidents[index]);
        }
      },
    });
  }

  _getScheduledMaintenance() {
    this.warehouseStatus.scheduled_maintenances({
      filter: "active",
      success: function (data) {
        for (incident in data.scheduled_maintenances) {
          this.unhide("active-maintenance");
          console.log(data);
          this.addIncident("active-maintenance",
            data.scheduled_maintenances[incident]);
        }
      },
    });
  }

  _formatUtcDateTime(time) {
    const date = new Date(time);
    return `${date.getUTCFullYear()}-${date.getUTCMonth()}-${date.getUTCDate()} ${date.getUTCHours()}:${date.getUTCMinutes()}:${date.getUTCSeconds()} UTC`;
  }

  _addIncident(type, incident) {
    const li = document.createElement("li");
    li.classList.add(`notification-bar__event`);

    const indicator = document.createElement("span");
    indicator.classList.add(`notification-bar__status--${incident.impact}`);
    indicator.classList.add(`fa`);
    indicator.classList.add(`fa-exclamation-circle`);

    li.appendChild(indicator);
    li.innerHTML += `[${incident.status}] - [Updated: ${this._formatUtcDateTime(incident.updated_at)}] - ${incident.name}`;
    this.eventsTarget.appendChild(li);

    // const x = document.getElementById(type);
    // elem = document.createElement("span");
    // link = document.createElement("a");
    // link.innerHTML = this.jsUcfirst(incident.status) + ": " + incident.name;
    // link.href = incident.shortlink;
    // link.classList.add("callout-block__link");
    // elem.appendChild(link);
    // x.appendChild(elem);
  }

  _getStatus() {
    this.warehouseStatus.status({
      success(data) {
        console.log(data);
      },
    });
  }

  connect() {
    if (this.mock) {
      this.warehouseStatus = MockStatusPage;
    } else if (StatusPage) {
      this.warehouseStatus = new StatusPage.page({
        page: "2p66nmmycsj3",
        component: "xt7f24hjvspn",
      });
    }

    this._getStatus();
    // this._getIncidents();
    // this._getScheduledMaintenance();
  }
}