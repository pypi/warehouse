/* SPDX-License-Identifier: Apache-2.0 */
/* global Chart */

$(function() {
  if (typeof Chart === "undefined") {
    return;
  }

  initProjectCreationsChart();
});

function initProjectCreationsChart() {
  const chartCanvas = document.getElementById("projectCreationsChart");
  const chartDataScript = document.getElementById("projectCreationsChartData");

  if (!chartCanvas || !chartDataScript) {
    return;
  }

  let chartData;
  try {
    chartData = JSON.parse(chartDataScript.textContent);
  } catch {
    return;
  }

  const labels = chartData.labels || [];
  const counts = chartData.counts || [];

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
          label: "Projects created",
          data: counts,
          backgroundColor: "rgba(23, 162, 184, 0.7)",
          borderColor: "rgb(23, 162, 184)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        xAxes: [{
          ticks: {
            maxTicksLimit: 15,
            maxRotation: 45,
            minRotation: 0,
          },
        }],
        yAxes: [{
          ticks: {
            beginAtZero: true,
            precision: 0,
            callback: function(value) {
              return value.toLocaleString();
            },
          },
        }],
      },
      tooltips: {
        callbacks: {
          label: function(tooltipItem) {
            return tooltipItem.yLabel.toLocaleString() + " projects";
          },
        },
      },
    },
  });
}
