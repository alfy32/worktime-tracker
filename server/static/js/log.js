const Log = (() => {
  const PER_PAGE = 50;
  let _page = 1;
  let _filterComputer = '';
  let _filterBound = false;
  let _modalBound = false;

  function fmtH(h) { return Charts.fmtH(h); }

  function fmtDT(isoStr) {
    const dt = new Date(isoStr);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
           dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  }

  async function load() {
    _page = 1;
    bindFilter();
    bindModal();
    await loadSessions();
    await loadManual();
  }

  // ── Sessions ────────────────────────────────────────────────────

  async function loadSessions() {
    try {
      const perPage = _filterComputer ? 5000 : PER_PAGE;
      const page = _filterComputer ? 1 : _page;
      const data = await api.getSessions(page, perPage);
      if (_filterComputer) {
        // Filter client-side, paginate the filtered result
        const filtered = data.sessions.filter(s => s.computer === _filterComputer);
        const total = filtered.length;
        const start = (_page - 1) * PER_PAGE;
        const paged = filtered.slice(start, start + PER_PAGE);
        renderSessions({ sessions: paged, total });
        renderPagination({ sessions: paged, total });
      } else {
        renderSessions(data);
        renderPagination(data);
      }
    } catch (e) {
      console.error('Log sessions error:', e);
    }
  }

  function renderSessions(data) {
    const tbody = document.getElementById('log-table-body');
    let sessions = data.sessions;

    if (!sessions.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="p-8 text-center text-slate-600">No sessions.</td></tr>';
      return;
    }

    tbody.innerHTML = sessions.map(s =>
      '<tr class="border-b border-slate-700 hover:bg-slate-700">' +
        '<td class="p-4 text-slate-300 whitespace-nowrap">' + fmtDT(s.login_at) + '</td>' +
        '<td class="p-4 text-slate-400">' + s.computer + '</td>' +
        '<td class="p-4 text-right text-slate-300 whitespace-nowrap">' + fmtH(s.duration_hours) + '</td>' +
        '<td class="p-4 text-center">' +
          '<button class="work-toggle text-xs px-2 py-0.5 rounded ' +
            (s.is_work ? 'bg-teal-900 text-teal-300 hover:bg-teal-800' : 'bg-slate-700 text-slate-400 hover:bg-slate-600') + '" ' +
            'data-id="' + s.id + '" data-is-work="' + s.is_work + '">' +
            (s.is_work ? 'Work' : 'Non-work') +
          '</button>' +
        '</td>' +
        '<td class="p-4 text-slate-500 text-xs hidden sm:table-cell">' + (s.note || '') + '</td>' +
      '</tr>'
    ).join('');

    tbody.querySelectorAll('.work-toggle').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id     = parseInt(btn.dataset.id);
        const isWork = btn.dataset.isWork === 'true';
        try {
          await api.patchSession(id, { is_work: !isWork, note: null });
          await loadSessions();
        } catch (e) { console.error('Toggle error:', e); }
      });
    });
  }

  function renderPagination(data) {
    const el = document.getElementById('log-pagination');
    const totalPages = Math.ceil(data.total / PER_PAGE);
    if (totalPages <= 1) { el.innerHTML = ''; return; }

    el.innerHTML =
      '<button id="pg-prev" class="px-3 py-1 rounded bg-slate-700 text-sm ' +
        (_page === 1 ? 'opacity-30 cursor-default' : 'hover:bg-slate-600') + '">&larr;</button>' +
      '<span class="text-slate-400">Page ' + _page + ' of ' + totalPages + '</span>' +
      '<button id="pg-next" class="px-3 py-1 rounded bg-slate-700 text-sm ' +
        (_page >= totalPages ? 'opacity-30 cursor-default' : 'hover:bg-slate-600') + '">&rarr;</button>';

    document.getElementById('pg-prev').addEventListener('click', async () => {
      if (_page > 1) { _page--; await loadSessions(); }
    });
    document.getElementById('pg-next').addEventListener('click', async () => {
      if (_page < totalPages) { _page++; await loadSessions(); }
    });
  }

  // ── Manual entries ───────────────────────────────────────────────

  async function loadManual() {
    try {
      const entries = await api.getManualEntries();
      renderManual(entries);
    } catch (e) { console.error('Manual entries error:', e); }
  }

  function renderManual(entries) {
    const el = document.getElementById('manual-list');
    if (!entries.length) {
      el.innerHTML = '<div class="text-slate-500 text-sm">No manual entries.</div>';
      return;
    }
    el.innerHTML = entries.map(e =>
      '<div class="flex items-center gap-3 py-2 border-b border-slate-700 last:border-0 text-sm">' +
        '<span class="text-slate-300 w-24 shrink-0">' + e.date + '</span>' +
        '<span class="text-slate-400 w-10 shrink-0">' + e.hours + 'h</span>' +
        '<span class="text-slate-500 flex-1">' + (e.note || '') + '</span>' +
        '<button class="del-btn text-red-400 hover:text-red-300 text-xs" data-id="' + e.id + '">Delete</button>' +
      '</div>'
    ).join('');

    el.querySelectorAll('.del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this manual entry?')) return;
        try {
          await api.deleteManualEntry(btn.dataset.id);
          await loadManual();
          // Refresh dashboard if visible
          if (document.getElementById('page-dashboard').classList.contains('active')) {
            Dashboard.load();
          }
        } catch (e) { console.error('Delete error:', e); }
      });
    });
  }

  // ── Modal ────────────────────────────────────────────────────────

  function bindModal() {
    if (_modalBound) {
      // Reset defaults each load even if already bound
      document.getElementById('manual-date').value = new Date().toISOString().slice(0, 10);
      document.getElementById('manual-hours').value = '8';
      document.getElementById('manual-note').value  = '';
      return;
    }
    _modalBound = true;
    const modal     = document.getElementById('modal-manual');
    const btnOpen   = document.getElementById('btn-add-manual');
    const btnCancel = document.getElementById('btn-modal-cancel');
    const btnSave   = document.getElementById('btn-modal-save');

    // Default date = today
    document.getElementById('manual-date').value = new Date().toISOString().slice(0, 10);
    document.getElementById('manual-hours').value = '8';
    document.getElementById('manual-note').value  = '';

    btnOpen.onclick = () => { modal.style.display = 'flex'; };
    btnCancel.onclick = closeModal;
    modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

    // Guard against duplicate listeners
    const newSave = btnSave.cloneNode(true);
    btnSave.parentNode.replaceChild(newSave, btnSave);
    newSave.addEventListener('click', async () => {
      const date  = document.getElementById('manual-date').value;
      const hours = parseFloat(document.getElementById('manual-hours').value);
      const note  = document.getElementById('manual-note').value.trim() || null;
      if (!date || isNaN(hours) || hours <= 0) {
        alert('Please enter a valid date and hours > 0.');
        return;
      }
      try {
        await api.addManualEntry({ date, hours, note });
        closeModal();
        await loadManual();
      } catch (e) { alert('Failed to save: ' + e.message); }
    });
  }

  function closeModal() {
    document.getElementById('modal-manual').style.display = 'none';
  }

  // ── Computer filter ──────────────────────────────────────────────

  function bindFilter() {
    if (_filterBound) return;
    _filterBound = true;
    document.getElementById('log-filter-computer').addEventListener('change', async e => {
      _filterComputer = e.target.value;
      _page = 1;
      await loadSessions();
    });
  }

  return { load };
})();
