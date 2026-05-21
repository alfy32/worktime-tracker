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
    const s = t.status;

    if (s.logged_in) {
      compEl.textContent = 'Logged in on ' + (s.computer || 'unknown');
      compEl.style.color = 'rgb(45,212,191)'; // teal-400
      detEl.textContent  = (s.since ? fmtAgo(s.since) + ' · ' : '') + fmtH(t.hours_worked) + ' today';
    } else {
      compEl.textContent = s.computer ? 'Logged out · ' + s.computer : 'No recent activity';
      compEl.style.color = '';
      detEl.textContent  = s.since ? 'Last seen ' + fmtAgo(s.since) : '';
    }

    const parts = Object.entries(t.per_computer)
      .map(([c, h]) => c + ' ' + fmtH(h));
    splitEl.textContent = parts.join(' · ');
  }

  function renderWeekCard(w) {
    document.getElementById('week-hours').textContent = fmtH(w.total_hours);
    document.getElementById('week-target').textContent =
      'Target ' + fmtH(w.adjusted_target) + ' · ' + fmtH(w.hours_remaining) + ' remaining';
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

  return { load };
})();
