/* Shared Chart.js setup for the admin analytics dashboard.
 *
 * Each chart reads a `[["Label", "Value"], ...]` payload from a json_script tag
 * rendered by the template, so no JSON is injected into inline scripts.
 */
const CHART_PALETTE = [
    "#a78bfa",
    "#f472b6",
    "#38bdf8",
    "#4ade80",
    "#facc15",
    "#fb923c",
    "#f87171",
    "#94a3b8",
];
const CHART_GRID_COLOR = "rgba(255, 255, 255, 0.08)";
const CHART_TICK_COLOR = "#a1a1aa";

function chartRows(dataId) {
    const element = document.getElementById(dataId);
    const payload = element ? JSON.parse(element.textContent) : [];
    const [header, ...rows] = payload;

    return { header: header ?? [], rows: rows };
}

function chartHasData(rows) {
    return rows.some((row) => Number(row[1]) > 0);
}

function showEmptyState(canvas) {
    if (!canvas) {
        return;
    }

    canvas.parentElement.innerHTML =
        '<div class="flex h-full items-center justify-center text-sm text-zinc-500">No data yet</div>';
}

function shortDate(isoDate) {
    return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
    });
}

function areaChart(canvasId, dataId) {
    const { header, rows } = chartRows(dataId);
    const canvas = document.getElementById(canvasId);

    if (!chartHasData(rows)) {
        showEmptyState(canvas);
        return;
    }

    new Chart(canvas, {
        type: "line",
        data: {
            labels: rows.map((row) => shortDate(row[0])),
            datasets: [
                {
                    label: header[1] ?? "Hours",
                    data: rows.map((row) => row[1]),
                    borderColor: CHART_PALETTE[0],
                    backgroundColor: "rgba(167, 139, 250, 0.25)",
                    fill: true,
                    tension: 0.25,
                    pointRadius: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 250 },
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    grid: { color: CHART_GRID_COLOR },
                    ticks: { color: CHART_TICK_COLOR, maxTicksLimit: 6, maxRotation: 0 },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: CHART_GRID_COLOR },
                    ticks: { color: CHART_TICK_COLOR },
                },
            },
        },
    });
}

function pieChart(canvasId, dataId, legend=true) {
    const { rows } = chartRows(dataId);
    const canvas = document.getElementById(canvasId);

    if (!chartHasData(rows)) {
        showEmptyState(canvas);
        return;
    }

    new Chart(canvas, {
        type: "pie",
        data: {
            labels: rows.map((row) => row[0]),
            datasets: [
                {
                    data: rows.map((row) => row[1]),
                    backgroundColor: CHART_PALETTE,
                    borderColor: "#18181b",
                    borderWidth: 1,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 250 },
            plugins: {
                legend: {
                    display: legend,
                    position: "bottom",
                    labels: { color: CHART_TICK_COLOR, boxWidth: 12, boxHeight: 12 },
                },
            },
        },
    });
}
