/* SPDX-License-Identifier: Apache-2.0 */
/* global Chart */

// Initialize observer charts if present on the page
$(function() {
  // Check if Chart.js is available
  if (typeof Chart === "undefined") {
    return;
  }

  // Dashboard chart (reputation page) - grouped bar chart
  initDashboardChart();

  // Observer detail chart - stacked bar chart
  initObserverDetailChart();
});

function initDashboardChart() {
  const chartCanvas = document.getElementById("reportsChart");
  const chartDataScript = document.getElementById("reportsChartData");

  if (!chartCanvas || !chartDataScript) {
    return;
  }

  let chartData;
  try {
    chartData = JSON.parse(chartDataScript.textContent);
  } catch (e) {
    return;
  }

  const labels = chartData.labels || [];
  const truePositives = chartData.truePositives || [];
  const falsePositives = chartData.falsePositives || [];
  const pending = chartData.pending || [];

  if (labels.length === 0) {
    return;
  }

  const ctx = chartCanvas.getContext("2d");

  new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "True Positives",
          data: truePositives,
          backgroundColor: "rgba(40, 167, 69, 0.8)",
          borderColor: "rgb(40, 167, 69)",
          borderWidth: 1,
        },
        {
          label: "False Positives",
          data: falsePositives,
          backgroundColor: "rgba(220, 53, 69, 0.8)",
          borderColor: "rgb(220, 53, 69)",
          borderWidth: 1,
        },
        {
          label: "Pending",
          data: pending,
          backgroundColor: "rgba(255, 193, 7, 0.8)",
          borderColor: "rgb(255, 193, 7)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        xAxes: [{
          stacked: true,
          scaleLabel: {
            display: true,
            labelString: "Week Starting",
          },
        }],
        yAxes: [{
          stacked: true,
          ticks: {
            beginAtZero: true,
          },
          scaleLabel: {
            display: true,
            labelString: "Number of Reports",
          },
        }],
      },
      legend: {
        position: "top",
      },
      tooltips: {
        mode: "index",
        intersect: false,
      },
    },
  });
}

function initObserverDetailChart() {
  const chartCanvas = document.getElementById("observerChart");
  const chartDataScript = document.getElementById("observerChartData");

  if (!chartCanvas || !chartDataScript) {
    return;
  }

  let chartData;
  try {
    chartData = JSON.parse(chartDataScript.textContent);
  } catch (e) {
    return;
  }

  const labels = chartData.labels || [];
  const truePositives = chartData.truePositives || [];
  const falsePositives = chartData.falsePositives || [];
  const pending = chartData.pending || [];

  if (labels.length === 0) {
    return;
  }

  const ctx = chartCanvas.getContext("2d");

  new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "True Positives",
          data: truePositives,
          backgroundColor: "rgba(40, 167, 69, 0.8)",
          borderColor: "rgb(40, 167, 69)",
          borderWidth: 1,
        },
        {
          label: "False Positives",
          data: falsePositives,
          backgroundColor: "rgba(220, 53, 69, 0.8)",
          borderColor: "rgb(220, 53, 69)",
          borderWidth: 1,
        },
        {
          label: "Pending",
          data: pending,
          backgroundColor: "rgba(255, 193, 7, 0.8)",
          borderColor: "rgb(255, 193, 7)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        xAxes: [{
          stacked: true,
          scaleLabel: {
            display: true,
            labelString: "Week Starting",
          },
        }],
        yAxes: [{
          stacked: true,
          ticks: {
            beginAtZero: true,
            stepSize: 1,
          },
          scaleLabel: {
            display: true,
            labelString: "Number of Reports",
          },
        }],
      },
      legend: {
        position: "top",
      },
      title: {
        display: false,
      },
      tooltips: {
        mode: "index",
        intersect: false,
      },
    },
  });
}
