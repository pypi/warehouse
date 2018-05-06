import { Controller } from "stimulus";

export default class extends Controller {
  static targets = ["title", "components", "incidents"];
  incidentLimit = 3;
  statusPageDomain = null;

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

      fetch(`${this.statusPageDomain}/api/v2/status.json`).then((response) => {
        return response.json();
      }).then((json) => {
        const description = json.status.description;
        // If we get something other than "none", this is not normal.
        // if (json.status.indicator !== "none") {
          return json.status.indicator;
        // }
      }).then((indicator) => {
        console.log(this);
        fetch(`${this.statusPageDomain}/api/v2/summary.json`)
          .then((response) => {
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
              console.log(this.incidentsTarget.parentNode);
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