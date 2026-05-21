const api = (() => {
  async function _fetch(path, options) {
    const opts = { ...options };
    if (opts.body) {
      opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(res.status + ': ' + text);
    }
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) return null;
    return res.json();
  }

  return {
    getTodaySummary:   ()           => _fetch('/api/summary/today'),
    getWeekSummary:    ()           => _fetch('/api/summary/week'),
    getDailySummary:   (days  = 60) => _fetch('/api/summary/daily?days='  + days),
    getWeeklySummary:  (weeks = 26) => _fetch('/api/summary/weekly?weeks=' + weeks),
    getSessions:       (page = 1, perPage = 50) =>
      _fetch('/api/sessions?page=' + page + '&per_page=' + perPage),
    patchSession:      (id, body)   => _fetch('/api/sessions/' + id, { method: 'PATCH', body: JSON.stringify(body) }),
    getManualEntries:  ()           => _fetch('/api/manual'),
    addManualEntry:    (body)       => _fetch('/api/manual',       { method: 'POST',   body: JSON.stringify(body) }),
    deleteManualEntry: (id)         => _fetch('/api/manual/' + id, { method: 'DELETE' }),
    getSettings:       ()           => _fetch('/api/settings'),
    updateSettings:    (body)       => _fetch('/api/settings',     { method: 'PUT',    body: JSON.stringify(body) }),
  };
})();
