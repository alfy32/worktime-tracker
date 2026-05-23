const Dashboard = (() => {
  function fmtTime(isoStr) {
    if (!isoStr) return null;
    return new Date(isoStr).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  }

  function fmtH(h) {
    return Charts.fmtH(h);
  }

  function fmtAgo(isoStr) {
    if (!isoStr) return '';
    const mins = (Date.now() - new Date(isoStr)) / 60000;
    if (mins < 60) return Math.round(mins) + 'm ago';
    const h = Math.floor(mins / 60), m = Math.round(mins % 60);
    return (m ? h + 'h ' + m + 'm' : h + 'h') + ' ago';
  }

  function isWeekend() {
    const d = new Date().getDay();
    return d === 0 || d === 6;
  }

  async function load() {
    try {
      const [today, week, daily] = await Promise.all([
        api.getTodaySummary(),
        api.getWeekSummary(),
        api.getDailySummary(10),
      ]);
      renderHero(today);
      renderStatus(today);
      renderWeekCard(week);
      renderRecentChart(daily);
      renderTodaySessions(today.sessions);
    } catch (e) {
      console.error('Dashboard error:', e);
      const el = document.getElementById('hero-sub');
      if (el) el.textContent = 'Error loading data.';
    }
  }

  function renderHero(t) {
    const mainEl = document.getElementById('hero-main');
    const subEl  = document.getElementById('hero-sub');
    const bankEl = document.getElementById('hero-bank');

    if (t.stop_time) {
      mainEl.textContent = 'Stop at ' + fmtTime(t.stop_time);
      mainEl.style.color = '';          // teal (from class)
      subEl.textContent  = fmtH(t.hours_remaining) + ' remaining';
    } else if (isWeekend()) {
      mainEl.textContent = 'Weekend';
      subEl.textContent  = t.hours_worked > 0
        ? 'Worked ' + fmtH(t.hours_worked) + ' today'
        : 'No target today';
    } else {
      mainEl.textContent = "You're done for today";
      subEl.textContent  = 'Worked ' + fmtH(t.hours_worked) + ' today';
    }

    const b = t.bank_hours;
    if (Math.abs(b) < 0.1) {
      bankEl.textContent = 'On track overall';
    } else if (b > 0) {
      bankEl.textContent = '+' + fmtH(b) + ' banked overall';
    } else {
      bankEl.textContent = fmtH(b) + ' behind overall';
    }
  }

  function renderStatus(t) {
    const compEl  = document.getElementById('status-computer');
    const detEl   = document.getElementById('status-detail');
    const splitEl = document.getElementById('status-split');

    const activeComputers = [...new Set((t.sessions || []).filter(s => s.is_active).map(s => s.computer))];

    if (activeComputers.length > 0) {
      const activeSessions = (t.sessions || []).filter(s => s.is_active);
      const mostRecent = activeSessions.sort((a, b) => new Date(b.login_at) - new Date(a.login_at))[0];
      compEl.textContent = 'Logged in · ' + activeComputers.join(', ');
      compEl.style.color = 'rgb(45,212,191)';
      detEl.textContent  = (mostRecent ? fmtAgo(mostRecent.login_at) + ' · ' : '') + fmtH(t.hours_worked) + ' today';
    } else {
      compEl.textContent = 'Logged out';
      compEl.style.color = '';
      detEl.textContent  = t.status.since ? 'Last seen ' + fmtAgo(t.status.since) : 'No recent activity';
    }

    const parts = Object.entries(t.per_computer).map(([c, h]) => c + ' ' + fmtH(h));
    splitEl.textContent = parts.join(' · ');
  }

  function renderWeekCard(w) {
    const remaining = Math.max(0, w.weekly_target - w.total_hours);
    document.getElementById('week-hours').textContent = fmtH(w.total_hours);
    document.getElementById('week-target').textContent =
      'Target ' + fmtH(w.weekly_target) + ' · ' + fmtH(remaining) + ' remaining';
    document.getElementById('week-remaining').textContent =
      w.remaining_weekdays + ' workday' + (w.remaining_weekdays !== 1 ? 's' : '') + ' left this week';
  }

  function renderRecentChart(daily) {
    const days   = daily.days.slice(-10);
    const labels = days.map(d => {
      const dt = new Date(d.date + 'T12:00:00');
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    Charts.makeOrUpdate('chart-recent', labels, days.map(d => d.hours), 8);
  }

  function renderTodaySessions(sessions) {
    const el = document.getElementById('today-sessions-list');
    if (el.querySelector('.ds-note:focus')) return; // don't disrupt active note editing
    if (!sessions || !sessions.length) {
      el.innerHTML = '<div class="px-4 py-3 text-slate-500 text-sm">No sessions today.</div>';
      return;
    }
    const sorted = sessions.slice().sort((a, b) => new Date(b.login_at) - new Date(a.login_at));

    el.innerHTML = sorted.map((s, idx) => {
      const start   = fmtTime(s.login_at);
      const end     = s.logout_at ? fmtTime(s.logout_at) : '<span class="text-teal-500">active</span>';
      const workCls = s.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400';
      return (
        '<div class="border-t border-slate-700">' +
          '<div class="flex items-center gap-3 px-4 py-3 text-sm flex-wrap">' +
            '<span class="text-slate-300 tabular-nums shrink-0">' + start + ' – ' + end + '</span>' +
            '<span class="text-teal-400 font-medium shrink-0">' + fmtH(s.duration_hours) + '</span>' +
            '<span class="text-slate-500 text-xs shrink-0">' + s.computer + '</span>' +
            '<button class="ds-work-toggle ml-auto text-xs px-2 py-0.5 rounded ' + workCls + '" data-idx="' + idx + '">' +
              (s.is_work ? 'Work' : 'Non-work') +
            '</button>' +
          '</div>' +
          '<div class="px-4 pb-3">' +
            '<input class="ds-note bg-transparent text-slate-400 text-xs w-full placeholder-slate-600 outline-none border-b border-transparent focus:border-slate-500 transition-colors" ' +
              'data-idx="' + idx + '" placeholder="Add note…">' +
          '</div>' +
        '</div>'
      );
    }).join('');

    // Set note values via DOM to avoid HTML-escaping issues
    sorted.forEach((s, idx) => {
      const input = el.querySelector('.ds-note[data-idx="' + idx + '"]');
      if (input) input.value = s.note || '';
    });

    el.querySelectorAll('.ds-work-toggle').forEach(btn => {
      btn.addEventListener('click', async () => {
        const s = sorted[parseInt(btn.dataset.idx)];
        try {
          await api.patchSession(s.id, { is_work: !s.is_work, note: s.note || null });
          Dashboard.load();
        } catch (e) { console.error('Toggle error:', e); }
      });
    });

    el.querySelectorAll('.ds-note').forEach(input => {
      const s = sorted[parseInt(input.dataset.idx)];
      input.addEventListener('blur', async () => {
        const newNote = input.value.trim() || null;
        if (newNote === (s.note || null)) return;
        try {
          await api.patchSession(s.id, { is_work: s.is_work, note: newNote });
          Dashboard.load();
        } catch (e) {
          console.error('Note error:', e);
          input.value = s.note || '';
        }
      });
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      });
    });
  }

  return { load };
})();
