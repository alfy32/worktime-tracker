const Weekly = (() => {
  const _weekCache = new Map();  // week_start string -> WeekDetail

  function fmtH(h) { return Charts.fmtH(Math.abs(h)); }

  function fmtWeek(dateStr) {
    const dt = new Date(dateStr + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function fmtDate(dateStr) {
    const dt = new Date(dateStr + 'T12:00:00');
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

  function fmtTime(isoStr) {
    return new Date(isoStr).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
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

    tbody.innerHTML = rows.map((w, i) => {
      const hourColor  = w.total_hours >= 40 ? 'text-teal-400' : w.total_hours > 0 ? 'text-orange-400' : 'text-slate-600';
      const delta      = w.delta_from_40;
      const deltaColor = delta >= 0 ? 'text-teal-400' : 'text-orange-400';
      const deltaStr   = w.total_hours > 0
        ? (delta >= 0 ? '+' : '−') + fmtH(delta)
        : '—';
      return (
        '<tr class="border-b border-slate-700 hover:bg-slate-700 cursor-pointer select-none" data-widx="' + i + '">' +
          '<td class="p-4 text-slate-500 text-lg leading-none">›</td>' +
          '<td class="p-4 font-medium">' + fmtWeek(w.week_start) + '</td>' +
          '<td class="p-4 text-right font-semibold ' + hourColor + '">' + (w.total_hours > 0 ? fmtH(w.total_hours) : '—') + '</td>' +
          '<td class="p-4 text-right text-slate-400 hidden md:table-cell">' + (w.avg_hours_per_day > 0 ? fmtH(w.avg_hours_per_day) : '—') + '</td>' +
          '<td class="p-4 text-right ' + deltaColor + ' hidden sm:table-cell">' + deltaStr + '</td>' +
        '</tr>' +
        '<tr id="wexpand-' + i + '" class="hidden bg-slate-850 border-b border-slate-700">' +
          '<td colspan="5" class="p-0"><div id="wdays-' + i + '"></div></td>' +
        '</tr>'
      );
    }).join('');

    tbody.querySelectorAll('[data-widx]').forEach(row => {
      row.addEventListener('click', () => toggleWeekRow(row, rows));
    });
  }

  async function toggleWeekRow(row, rows) {
    const wi = parseInt(row.dataset.widx);
    const expandRow = document.getElementById('wexpand-' + wi);
    const arrow = row.querySelector('td:first-child');
    const isOpen = !expandRow.classList.contains('hidden');

    if (isOpen) {
      expandRow.classList.add('hidden');
      if (arrow) arrow.textContent = '›';
      return;
    }

    const weekStart = rows[wi].week_start;
    let detail = _weekCache.get(weekStart);
    if (!detail) {
      try {
        detail = await api.getWeekDetail(weekStart);
        _weekCache.set(weekStart, detail);
      } catch (e) {
        console.error('Week detail error:', e);
        return;
      }
    }

    renderDays(wi, detail.days);
    expandRow.classList.remove('hidden');
    if (arrow) arrow.textContent = '⌄';
  }

  function renderDays(wi, days) {
    const container = document.getElementById('wdays-' + wi);
    container.innerHTML =
      '<table class="w-full text-xs"><tbody>' +
      days.map((d, di) => {
        const hasContent = d.sessions.length > 0 || d.manual_entries.length > 0;
        const color = d.hours >= 8 ? 'text-teal-400' : d.hours > 0 ? 'text-orange-400' : 'text-slate-600';
        return (
          '<tr class="border-b border-slate-800' +
            (hasContent ? ' hover:bg-slate-750 cursor-pointer select-none' : '') + '"' +
            (hasContent ? ' data-widx="' + wi + '" data-didx="' + di + '"' : '') + '>' +
            '<td class="pl-6 py-2 text-slate-500 text-base leading-none">' + (hasContent ? '›' : '') + '</td>' +
            '<td class="py-2 font-medium text-slate-300">' + fmtDate(d.date) + '</td>' +
            '<td class="py-2 text-right font-semibold ' + color + '">' + (d.hours > 0 ? fmtH(d.hours) : '—') + '</td>' +
            '<td class="py-2 text-right text-slate-500 hidden sm:table-cell">' + (d.session_count > 0 ? d.session_count + ' sessions' : '—') + '</td>' +
          '</tr>' +
          '<tr id="wdexpand-' + wi + '-' + di + '" class="hidden bg-slate-900">' +
            '<td colspan="4" class="px-10 py-2"><div id="wsess-' + wi + '-' + di + '" class="space-y-2"></div></td>' +
          '</tr>'
        );
      }).join('') +
      '</tbody></table>';

    container.querySelectorAll('[data-didx]').forEach(row => {
      const di = parseInt(row.dataset.didx);
      row.addEventListener('click', () => toggleDayRow(wi, di, days[di]));
    });
  }

  function toggleDayRow(wi, di, day) {
    const expandRow = document.getElementById('wdexpand-' + wi + '-' + di);
    const dayRow = expandRow.previousElementSibling;
    const arrow = dayRow ? dayRow.querySelector('td:first-child') : null;
    const isOpen = !expandRow.classList.contains('hidden');

    if (isOpen) {
      expandRow.classList.add('hidden');
      if (arrow) arrow.textContent = '›';
      return;
    }

    renderSessions(wi, di, day);
    expandRow.classList.remove('hidden');
    if (arrow) arrow.textContent = '⌄';
  }

  function renderSessions(wi, di, day) {
    const _td = new Date();
    const todayStr = _td.getFullYear() + '-' +
      String(_td.getMonth() + 1).padStart(2, '0') + '-' +
      String(_td.getDate()).padStart(2, '0');
    const isPastDay = day.date < todayStr;

    const sessions = day.sessions.slice().sort((a, b) => new Date(a.login_at) - new Date(b.login_at));
    const container = document.getElementById('wsess-' + wi + '-' + di);

    const sessionRows = sessions.map((s, si) => {
      const badgeCls = 'sess-toggle px-2 py-0.5 rounded text-xs ' +
        (s.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400');
      const badgeLabel = s.is_work ? 'Work' : 'Non-work';
      const endTime = s.logout_at
        ? fmtTime(s.logout_at)
        : (isPastDay
            ? '<span class="text-orange-400">never ended</span>'
            : '<span class="text-teal-500">active</span>');
      const dur = s.is_active && isPastDay ? '—' : fmtH(s.duration_hours);
      return (
        '<div class="py-1.5 text-xs border-b border-slate-800 last:border-0">' +
          '<div class="flex items-center gap-2">' +
            '<span class="text-slate-400 shrink-0">' + fmtTime(s.login_at) + ' – ' + endTime + '</span>' +
            '<span class="text-slate-500 shrink-0 w-10">' + dur + '</span>' +
            '<span class="text-slate-500 shrink-0">' + s.computer + '</span>' +
            '<button class="' + badgeCls + ' ml-auto hidden sm:inline-flex" data-sidx="' + si + '">' + badgeLabel + '</button>' +
          '</div>' +
          '<div class="mt-1 sm:hidden">' +
            '<button class="' + badgeCls + '" data-sidx="' + si + '">' + badgeLabel + '</button>' +
          '</div>' +
          '<div class="mt-1">' +
            '<input class="sess-note bg-transparent text-slate-400 text-xs w-full placeholder-slate-600 outline-none border-b border-transparent focus:border-slate-500 transition-colors" ' +
              'data-sidx="' + si + '" placeholder="Add note…">' +
          '</div>' +
        '</div>'
      );
    });

    const manualRows = day.manual_entries.map(m =>
      '<div class="flex items-center gap-3 text-xs py-1 flex-wrap">' +
        '<span class="text-slate-400 shrink-0">manual</span>' +
        '<span class="text-slate-500 shrink-0 w-10">' + fmtH(m.hours) + '</span>' +
        '<span class="px-2 py-0.5 rounded bg-slate-700 text-slate-400">Manual</span>' +
        (m.note ? '<span class="text-slate-500">' + m.note + '</span>' : '') +
      '</div>'
    );

    container.innerHTML = [...sessionRows, ...manualRows].join('');

    // Set note values via DOM to avoid HTML-escaping issues
    sessions.forEach((s, si) => {
      const input = container.querySelector('.sess-note[data-sidx="' + si + '"]');
      if (input) input.value = s.note || '';
    });

    container.querySelectorAll('.sess-toggle').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const si = parseInt(btn.dataset.sidx);
        const session = sessions[si];
        const newIsWork = !session.is_work;
        try {
          const updated = await api.patchSession(session.id, { is_work: newIsWork, note: session.note });
          session.is_work = updated.is_work;
          const newCls = 'sess-toggle px-2 py-0.5 rounded text-xs ' +
            (updated.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400');
          const newLabel = updated.is_work ? 'Work' : 'Non-work';
          container.querySelectorAll('.sess-toggle[data-sidx="' + si + '"]').forEach(b => {
            b.textContent = newLabel;
            b.className = newCls;
          });
        } catch (err) {
          console.error('Toggle error:', err);
        }
      });
    });

    container.querySelectorAll('.sess-note').forEach(input => {
      const si = parseInt(input.dataset.sidx);
      const session = sessions[si];
      input.addEventListener('blur', async () => {
        const newNote = input.value.trim() || null;
        if (newNote === (session.note || null)) return;
        try {
          await api.patchSession(session.id, { is_work: session.is_work, note: newNote });
          session.note = newNote;
        } catch (err) {
          console.error('Note error:', err);
          input.value = session.note || '';
        }
      });
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      });
    });
  }

  return { load };
})();
