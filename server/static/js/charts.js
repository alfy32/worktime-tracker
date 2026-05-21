const Charts = (() => {
  const TEAL   = 'rgba(20,  184, 166, 0.85)';
  const ORANGE = 'rgba(249, 115,  22, 0.85)';
  const REF    = 'rgba(148, 163, 184, 0.35)';

  function barColors(values, target) {
    return values.map(v => (v >= target ? TEAL : ORANGE));
  }

  /**
   * Create or replace a Chart.js bar chart on `canvasId`.
   * `target` draws a dashed reference line (default 8h for daily, pass 40 for weekly).
   * Returns the Chart instance.
   */
  function makeOrUpdate(canvasId, labels, values, target) {
    if (target === undefined) target = 8;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();

    return new Chart(canvas, {
      data: {
        labels: labels,
        datasets: [
          {
            type: 'bar',
            data: values,
            backgroundColor: barColors(values, target),
            borderRadius: 4,
            borderSkipped: false,
            order: 2,
          },
          {
            type: 'line',
            data: Array(labels.length).fill(target),
            borderColor: REF,
            borderWidth: 1.5,
            borderDash: [5, 4],
            pointRadius: 0,
            fill: false,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: item => item.datasetIndex === 0,
            callbacks: {
              label: ctx => fmtH(ctx.raw),
            },
          },
        },
        scales: {
          x: {
            grid:  { color: 'rgba(148,163,184,0.07)' },
            ticks: { color: '#64748b', font: { size: 11 }, maxRotation: 0 },
          },
          y: {
            grid:        { color: 'rgba(148,163,184,0.07)' },
            ticks:       { color: '#64748b', font: { size: 11 } },
            beginAtZero: true,
          },
        },
      },
    });
  }

  function fmtH(h) {
    const hh = Math.floor(Math.abs(h));
    const mm = Math.round((Math.abs(h) - hh) * 60);
    if (hh === 0) return mm + 'm';
    if (mm === 0) return hh + 'h';
    return hh + 'h ' + mm + 'm';
  }

  return { makeOrUpdate, fmtH };
})();
