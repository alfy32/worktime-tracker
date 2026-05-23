const Weekly = (() => {
  function fmtH(h) { return Charts.fmtH(Math.abs(h)); }

  function fmtWeek(dateStr) {
    const dt = new Date(dateStr + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  async function load() {
    try {
      const weekly = await api.getWeeklySummary(26);
      renderChart(weekly);
      renderTable(weekly);
    } catch (e) {
      console.error('Weekly error:', e);
    }
  }

  function renderChart(weekly) {
    const weeks  = weekly.weeks;
    const labels = weeks.map(w => fmtWeek(w.week_start));
    Charts.makeOrUpdate('chart-weekly', labels, weeks.map(w => w.total_hours), 40);
  }

  function renderTable(weekly) {
    const tbody = document.getElementById('weekly-table-body');
    const rows  = weekly.weeks.slice().reverse();

    tbody.innerHTML = rows.map(w => {
      const hourColor  = w.total_hours >= 40 ? 'text-teal-400' : w.total_hours > 0 ? 'text-orange-400' : 'text-slate-600';
      const delta      = w.delta_from_40;
      const deltaColor = delta >= 0 ? 'text-teal-400' : 'text-orange-400';
      const deltaStr   = w.total_hours > 0
        ? (delta >= 0 ? '+' : '−') + fmtH(delta)
        : '—';
      return (
        '<tr class="border-b border-slate-700 hover:bg-slate-700">' +
          '<td class="p-4 font-medium">' + fmtWeek(w.week_start) + '</td>' +
          '<td class="p-4 text-right font-semibold ' + hourColor + '">' + (w.total_hours > 0 ? fmtH(w.total_hours) : '—') + '</td>' +
          '<td class="p-4 text-right text-slate-400 hidden md:table-cell">' + (w.avg_hours_per_day > 0 ? fmtH(w.avg_hours_per_day) : '—') + '</td>' +
          '<td class="p-4 text-right ' + deltaColor + ' hidden sm:table-cell">' + deltaStr + '</td>' +
        '</tr>'
      );
    }).join('');
  }

  return { load };
})();
