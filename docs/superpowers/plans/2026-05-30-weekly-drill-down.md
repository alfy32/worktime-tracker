# Weekly Drill-Down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-level expand/collapse to the weekly view — click a week to show its days, click a day to show its sessions with full work/non-work toggle and note editing.

**Architecture:** A new `GET /api/summary/week/{week_start}` endpoint returns a full week breakdown with embedded sessions and manual entries per day. The frontend fetches this lazily on first expand and caches it in a `Map` keyed by `week_start`, so subsequent expands are instant and data volume per request is bounded to one week forever.

**Tech Stack:** Python/FastAPI + Pydantic (backend), vanilla JS + Tailwind (frontend), pytest + freezegun (tests)

---

### Task 1: Add Pydantic schemas for the new endpoint

**Files:**
- Modify: `server/schemas.py`

- [ ] **Step 1: Add `DayDetail` and `WeekDetail` schemas to `server/schemas.py`**

Add after the `DayStats` class (around line 73):

```python
class DayDetail(BaseModel):
    date: date
    hours: float
    session_count: int
    longest_break_hours: float
    is_invalid: bool = False
    sessions: list[SessionOut]
    manual_entries: list[ManualEntryOut]


class WeekDetail(BaseModel):
    week_start: date
    days: list[DayDetail]
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest tests/test_summary.py -v
```

Expected: all tests PASS (no schema changes break existing routes).

- [ ] **Step 3: Commit**

```bash
git add server/schemas.py
git commit -m "feat: add DayDetail and WeekDetail schemas for weekly drill-down"
```

---

### Task 2: Add the backend endpoint

**Files:**
- Modify: `server/routers/summary.py`
- Modify: `tests/test_summary.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_summary.py`:

```python
@freeze_time("2026-05-20 14:00:00")
def test_week_detail_returns_days_with_sessions(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-19T09:00:00", "action": "login"},
        {"timestamp": "2026-05-19T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/week/2026-05-18")
    assert resp.status_code == 200
    data = resp.json()
    assert data["week_start"] == "2026-05-18"
    # Mon May 18, Tue May 19, Wed May 20 — today is May 20
    assert len(data["days"]) == 3
    may19 = next(d for d in data["days"] if d["date"] == "2026-05-19")
    assert may19["hours"] == pytest.approx(8.0)
    assert may19["session_count"] == 1
    assert len(may19["sessions"]) == 1
    assert may19["sessions"][0]["computer"] == "ubuntu"
    assert may19["sessions"][0]["is_work"] is True
    assert may19["sessions"][0]["login_at"].startswith("2026-05-19T09:00")
    assert may19["sessions"][0]["logout_at"].startswith("2026-05-19T17:00")


@freeze_time("2026-05-20 14:00:00")
def test_week_detail_empty_days_have_no_sessions(client):
    resp = client.get("/api/summary/week/2026-05-18")
    assert resp.status_code == 200
    data = resp.json()
    for day in data["days"]:
        assert day["sessions"] == []
        assert day["manual_entries"] == []
        assert day["hours"] == 0.0


@freeze_time("2026-05-20 14:00:00")
def test_week_detail_includes_manual_entries(client):
    client.post("/api/manual", json={"date": "2026-05-19", "hours": 2.0, "note": "training"})
    resp = client.get("/api/summary/week/2026-05-18")
    data = resp.json()
    may19 = next(d for d in data["days"] if d["date"] == "2026-05-19")
    assert may19["hours"] == pytest.approx(2.0)
    assert len(may19["manual_entries"]) == 1
    assert may19["manual_entries"][0]["note"] == "training"
    assert may19["manual_entries"][0]["hours"] == 2.0


@freeze_time("2026-05-20 14:00:00")
def test_week_detail_only_includes_days_up_to_today(client):
    resp = client.get("/api/summary/week/2026-05-18")
    data = resp.json()
    dates = [d["date"] for d in data["days"]]
    assert "2026-05-18" in dates   # Mon
    assert "2026-05-19" in dates   # Tue
    assert "2026-05-20" in dates   # Wed (today)
    assert "2026-05-21" not in dates  # Thu (future)
    assert len(data["days"]) == 3


@freeze_time("2026-05-20 14:00:00")
def test_week_detail_longest_break(client):
    seed_events(client, "ubuntu", [
        {"timestamp": "2026-05-19T08:00:00", "action": "login"},
        {"timestamp": "2026-05-19T12:00:00", "action": "logout"},
        {"timestamp": "2026-05-19T13:30:00", "action": "login"},
        {"timestamp": "2026-05-19T17:00:00", "action": "logout"},
    ])
    resp = client.get("/api/summary/week/2026-05-18")
    data = resp.json()
    may19 = next(d for d in data["days"] if d["date"] == "2026-05-19")
    assert may19["longest_break_hours"] == pytest.approx(1.5)
    assert may19["session_count"] == 2
    assert len(may19["sessions"]) == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest tests/test_summary.py::test_week_detail_returns_days_with_sessions -v
```

Expected: FAIL with `404` (endpoint doesn't exist yet).

- [ ] **Step 3: Add the endpoint to `server/routers/summary.py`**

Update the imports at the top of `server/routers/summary.py` — add `DayDetail, WeekDetail, ManualEntryOut` to the schemas import:

```python
from schemas import (
    TodaySummary, WeekSummary, DailySummary, WeeklySummary,
    SessionOut, ComputerStatus, DayBreakdown, DayStats, WeekStats,
    DayDetail, WeekDetail, ManualEntryOut,
)
```

Then add this route at the end of `server/routers/summary.py`:

```python
@router.get("/api/summary/week/{week_start}", response_model=WeekDetail)
def summary_week_detail(week_start: date, db: Session = Depends(get_db)):
    now = datetime.now()
    today = now.date()

    all_events = db.query(Event).all()
    unclosed_ids = find_unclosed_login_ids(all_events, today)
    valid_all = [e for e in all_events if e.id not in unclosed_ids]

    # Build sessions once from each pool to correctly handle cross-midnight sessions.
    # Filter per day by login_at.date() to assign each session to its start day.
    sessions_valid = build_sessions(valid_all, now)
    sessions_today = build_sessions(all_events, now)

    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break

        d_manual = _day_manual(db, d)
        day_start = datetime.combine(d, datetime.min.time())
        end_of_day = datetime.combine(d + timedelta(days=1), datetime.min.time())
        cutoff = now if d == today else end_of_day
        ev_pool = all_events if d == today else valid_all

        hours = calculate_work_hours_in_window(ev_pool, d_manual, day_start, cutoff, now)

        sessions_pool = sessions_today if d == today else sessions_valid
        day_sessions = [s for s in sessions_pool if s.login_at.date() == d]

        is_invalid = d < today and any(
            e.id in unclosed_ids and e.timestamp.date() == d for e in all_events
        )

        days.append(DayDetail(
            date=d,
            hours=round(hours, 2),
            session_count=len(day_sessions),
            longest_break_hours=_longest_break_in_window(ev_pool, day_start, cutoff, now),
            is_invalid=is_invalid,
            sessions=day_sessions,
            manual_entries=d_manual,
        ))

    return WeekDetail(week_start=week_start, days=days)
```

- [ ] **Step 4: Run the new tests**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest tests/test_summary.py -v
```

Expected: all tests PASS including the 5 new ones.

- [ ] **Step 5: Commit**

```bash
git add server/routers/summary.py tests/test_summary.py
git commit -m "feat: add GET /api/summary/week/{week_start} endpoint for weekly drill-down"
```

---

### Task 3: Frontend glue — api.js and index.html

**Files:**
- Modify: `server/static/js/api.js`
- Modify: `server/static/index.html`

- [ ] **Step 1: Add `getWeekDetail` to `server/static/js/api.js`**

In `api.js`, add one line inside the `return { ... }` object after `getWeeklySummary`:

```js
getWeekDetail:     (weekStart)   => _fetch('/api/summary/week/' + weekStart),
```

The full return block should now read:

```js
  return {
    getTodaySummary:   ()           => _fetch('/api/summary/today'),
    getWeekSummary:    ()           => _fetch('/api/summary/week'),
    getDailySummary:   (days  = 60) => _fetch('/api/summary/daily?days='  + days),
    getWeeklySummary:  (weeks = 26) => _fetch('/api/summary/weekly?weeks=' + weeks),
    getWeekDetail:     (weekStart)  => _fetch('/api/summary/week/' + weekStart),
    getComputers:      ()           => _fetch('/api/sessions/computers'),
    getSessions:       (page = 1, perPage = 50) =>
      _fetch('/api/sessions?page=' + page + '&per_page=' + perPage),
    patchSession:      (id, body)   => _fetch('/api/sessions/' + id, { method: 'PATCH', body: JSON.stringify(body) }),
    getManualEntries:  ()           => _fetch('/api/manual'),
    addManualEntry:    (body)       => _fetch('/api/manual',       { method: 'POST',   body: JSON.stringify(body) }),
    deleteManualEntry: (id)         => _fetch('/api/manual/' + id, { method: 'DELETE' }),
    getSettings:       ()           => _fetch('/api/settings'),
    updateSettings:    (body)       => _fetch('/api/settings',     { method: 'PUT',    body: JSON.stringify(body) }),
  };
```

- [ ] **Step 2: Add the arrow `<th>` column to the weekly table header in `server/static/index.html`**

Find the weekly table `<thead>` block (around line 129) and replace it:

Old:
```html
          <thead class="text-slate-500 border-b border-slate-700 text-xs uppercase tracking-wide">
            <tr>
              <th class="text-left p-4">Week of</th>
              <th class="text-right p-4">Total Hours</th>
              <th class="text-right p-4 hidden md:table-cell">Avg / Day</th>
              <th class="text-right p-4 hidden sm:table-cell">vs 40h</th>
            </tr>
          </thead>
```

New:
```html
          <thead class="text-slate-500 border-b border-slate-700 text-xs uppercase tracking-wide">
            <tr>
              <th class="text-left p-4 w-8"></th>
              <th class="text-left p-4">Week of</th>
              <th class="text-right p-4">Total Hours</th>
              <th class="text-right p-4 hidden md:table-cell">Avg / Day</th>
              <th class="text-right p-4 hidden sm:table-cell">vs 40h</th>
            </tr>
          </thead>
```

- [ ] **Step 3: Commit**

```bash
git add server/static/js/api.js server/static/index.html
git commit -m "feat: add getWeekDetail API method and arrow column to weekly table header"
```

---

### Task 4: Rewrite weekly.js with full drill-down

**Files:**
- Modify: `server/static/js/weekly.js`

This replaces the entire file. The new version adds a `_weekCache` Map, a `toggleWeekRow` async function that fetches/caches week data and renders a nested day table, and a `toggleDayRow` + `renderSessions` pair that shows session rows with the same work/non-work toggle and note editing as the daily view.

- [ ] **Step 1: Replace `server/static/js/weekly.js` with the full implementation**

```js
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
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

```bash
cd /home/alan/projects/personal/worktime-tracker
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add server/static/js/weekly.js
git commit -m "feat: add two-level drill-down to weekly view with lazy loading and session editing"
```

---

### Task 5: Manual verification in the browser

- [ ] **Step 1: Start the server**

```bash
cd /home/alan/projects/personal/worktime-tracker
uvicorn server.main:app --reload --app-dir server
```

Or via docker-compose if that's the normal workflow:
```bash
docker-compose up
```

- [ ] **Step 2: Open the Weekly tab and verify**

1. Each week row should have a `›` arrow in the first column
2. Click a week row — arrow changes to `⌄`, nested day rows appear showing Mon–Sun (up to today)
3. Days with sessions have a `›` arrow; empty days do not
4. Click a day with sessions — sessions expand below showing time range, duration, computer, Work/Non-work badge, note field
5. Toggle the Work/Non-work badge — badge updates immediately, change persists on refresh
6. Edit a note, press Enter or click away — change persists on refresh
7. Click the week row again — collapses the entire week including any open day expands
8. Re-expand the same week — uses cache (no network request to `/api/summary/week/...`)
9. Expand a second week simultaneously — both stay open independently
