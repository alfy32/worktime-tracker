const Daily = (() => {
  let _sessions = [];   // all sessions fetched once, filtered in JS
  let _manuals  = [];   // all manual entries fetched once

  function fmtH(h) { return Charts.fmtH(h); }

  function fmtDate(dateStr) {
    const dt = new Date(dateStr + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

  function fmtTime(isoStr) {
    return new Date(isoStr).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  }

  function sessionsForDate(dateStr) {
    return _sessions.filter(s => s.login_at.startsWith(dateStr));
  }

  function manualsForDate(dateStr) {
    return _manuals.filter(m => m.date === dateStr);
  }

  async function load() {
    try {
      const [daily, sessResp, manuals] = await Promise.all([
        api.getDailySummary(60),
        api.getSessions(1, 5000),
        api.getManualEntries(),
      ]);
      _sessions = sessResp.sessions;
      _manuals  = manuals;
      renderChart(daily);
      renderTable(daily);
    } catch (e) {
      console.error('Daily error:', e);
    }
  }

  function renderChart(daily) {
    const labels = daily.days.map(d => {
      const dt = new Date(d.date + 'T12:00:00');
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    Charts.makeOrUpdate('chart-daily', labels, daily.days.map(d => d.hours), 8);
  }

  function renderTable(daily) {
    const tbody = document.getElementById('daily-table-body');
    // Most-recent first
    const rows = daily.days.slice().reverse();

    tbody.innerHTML = rows.map((d, i) => {
      const hasSessions = sessionsForDate(d.date).length > 0;
      const hasManuals  = manualsForDate(d.date).length > 0;
      const expandable  = hasSessions || hasManuals;
      const color = d.hours >= 8 ? 'text-teal-400'
                  : d.hours > 0  ? 'text-orange-400'
                  : 'text-slate-600';
      return (
        '<tr class="border-b border-slate-700 hover:bg-slate-700 cursor-pointer select-none" data-ridx="' + i + '">' +
          '<td class="p-4 text-slate-500 text-lg leading-none">' + (expandable ? '›' : '') + '</td>' +
          '<td class="p-4 font-medium">'  + fmtDate(d.date) + '</td>' +
          '<td class="p-4 text-right font-semibold ' + color + '">' + (d.hours > 0 ? fmtH(d.hours) : '—') + '</td>' +
          '<td class="p-4 text-right text-slate-400 hidden sm:table-cell">' + d.session_count + '</td>' +
          '<td class="p-4 text-right text-slate-400 hidden md:table-cell">' + (d.longest_break_hours > 0 ? fmtH(d.longest_break_hours) : '—') + '</td>' +
        '</tr>' +
        '<tr id="expand-' + i + '" class="hidden bg-slate-900 border-b border-slate-700">' +
          '<td colspan="5" class="px-8 py-3"><div id="sess-' + i + '" class="space-y-2"></div></td>' +
        '</tr>'
      );
    }).join('');

    tbody.querySelectorAll('[data-ridx]').forEach(row => {
      row.addEventListener('click', () => toggleRow(row, rows));
    });
  }

  function toggleRow(row, rows) {
    const i = parseInt(row.dataset.ridx);
    const expandRow = document.getElementById('expand-' + i);
    const isOpen = !expandRow.classList.contains('hidden');

    // Update arrow indicator
    const arrow = row.querySelector('td:first-child');

    if (isOpen) {
      expandRow.classList.add('hidden');
      if (arrow) arrow.textContent = '›';
      return;
    }

    const dateStr = rows[i].date;
    const _td = new Date();
    const todayStr = _td.getFullYear() + '-' +
      String(_td.getMonth() + 1).padStart(2, '0') + '-' +
      String(_td.getDate()).padStart(2, '0');
    const isPastDay = dateStr < todayStr;
    const sessions = sessionsForDate(dateStr).slice().sort((a, b) => new Date(a.login_at) - new Date(b.login_at));
    const manuals  = manualsForDate(dateStr);
    if (!sessions.length && !manuals.length) return;

    const container = document.getElementById('sess-' + i);
    const sessionRows = sessions.map((s, si) =>
      '<div class="flex items-center gap-3 text-xs py-1 flex-wrap" id="sr-' + i + '-' + si + '">' +
        '<span class="text-slate-400 shrink-0">' +
          fmtTime(s.login_at) + ' – ' + (
            s.logout_at
              ? fmtTime(s.logout_at)
              : (isPastDay
                  ? '<span class="text-orange-400">never ended</span>'
                  : '<span class="text-teal-500">active</span>')
          ) +
        '</span>' +
        '<span class="text-slate-500 shrink-0 w-10">' + (s.is_active && isPastDay ? '—' : fmtH(s.duration_hours)) + '</span>' +
        '<span class="text-slate-500 shrink-0">' + s.computer + '</span>' +
        '<button class="sess-toggle px-2 py-0.5 rounded text-xs ' +
          (s.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400') + '" ' +
          'data-ridx="' + i + '" data-sidx="' + si + '">' +
          (s.is_work ? 'Work' : 'Non-work') +
        '</button>' +
        (s.note ? '<span class="text-slate-500">' + s.note + '</span>' : '') +
      '</div>'
    );
    const manualRows = manuals.map(m =>
      '<div class="flex items-center gap-3 text-xs py-1 flex-wrap">' +
        '<span class="text-slate-400 shrink-0">manual</span>' +
        '<span class="text-slate-500 shrink-0 w-10">' + fmtH(m.hours) + '</span>' +
        '<span class="px-2 py-0.5 rounded bg-slate-700 text-slate-400">Manual</span>' +
        (m.note ? '<span class="text-slate-500">' + m.note + '</span>' : '') +
      '</div>'
    );
    container.innerHTML = [...sessionRows, ...manualRows].join('');

    container.querySelectorAll('.sess-toggle').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const ri = parseInt(btn.dataset.ridx);
        const si = parseInt(btn.dataset.sidx);
        const session = sessionsForDate(rows[ri].date)[si];
        const newIsWork = !session.is_work;
        try {
          const updated = await api.patchSession(session.id, { is_work: newIsWork, note: session.note });
          session.is_work = updated.is_work;
          btn.textContent = updated.is_work ? 'Work' : 'Non-work';
          btn.className = 'sess-toggle px-2 py-0.5 rounded text-xs ' +
            (updated.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400');
          // Refresh chart since hours changed
          const daily = await api.getDailySummary(60);
          renderChart(daily);
        } catch (err) {
          console.error('Toggle error:', err);
        }
      });
    });

    expandRow.classList.remove('hidden');
    if (arrow) arrow.textContent = '⌄';
  }

  return { load };
})();
