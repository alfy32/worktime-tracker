# Session Notes + Mobile Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline note editing to the daily view's session rows, and fix the Work/Non-work badge wrapping inconsistently on mobile in both the daily view and dashboard.

**Architecture:** Pure frontend change — no backend modifications needed. Both files rewrite their session row HTML to use a two-row desktop layout (info + badge on row 1, note input on row 2) and a three-row mobile layout (info on row 1, badge on row 2, note on row 3) using Tailwind `sm:` breakpoint classes to render the badge twice (hidden/visible per breakpoint). Note editing reuses the dashboard's existing blur/Enter-to-save pattern.

**Tech Stack:** Vanilla JS, Tailwind CSS (CDN), existing `api.patchSession(id, { is_work, note })` endpoint.

---

## Files

| File | Change |
|------|--------|
| `server/static/js/daily.js` | Rewrite session row HTML in `toggleRow()`; update toggle handler to sync both badge buttons; add note blur/keydown handlers |
| `server/static/js/dashboard.js` | Rewrite session row HTML in `renderTodaySessions()` with same responsive structure |

---

### Task 1: Update `daily.js` — responsive session rows with note editing

**Files:**
- Modify: `server/static/js/daily.js` (function `toggleRow`, lines ~65–115)

The `toggleRow` function currently builds session rows as a single `flex-wrap` div. Replace it with a structured block: two rows on desktop, three rows on mobile. Also update the toggle handler to sync both badge buttons (mobile + desktop), and add note input handlers.

- [ ] **Step 1: Replace the `sessionRows` map in `toggleRow()`**

Find this block in `server/static/js/daily.js` (inside `toggleRow`):

```js
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
```

Replace it with:

```js
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
        '<div class="py-1.5 text-xs border-b border-slate-800 last:border-0" id="sr-' + i + '-' + si + '">' +
          '<div class="flex items-center gap-2">' +
            '<span class="text-slate-400 shrink-0">' + fmtTime(s.login_at) + ' – ' + endTime + '</span>' +
            '<span class="text-slate-500 shrink-0 w-10">' + dur + '</span>' +
            '<span class="text-slate-500 shrink-0">' + s.computer + '</span>' +
            '<button class="' + badgeCls + ' ml-auto hidden sm:inline-flex" data-ridx="' + i + '" data-sidx="' + si + '">' + badgeLabel + '</button>' +
          '</div>' +
          '<div class="mt-1 sm:hidden">' +
            '<button class="' + badgeCls + '" data-ridx="' + i + '" data-sidx="' + si + '">' + badgeLabel + '</button>' +
          '</div>' +
          '<div class="mt-1">' +
            '<input class="sess-note bg-transparent text-slate-400 text-xs w-full placeholder-slate-600 outline-none border-b border-transparent focus:border-slate-500 transition-colors" ' +
              'data-ridx="' + i + '" data-sidx="' + si + '" placeholder="Add note…">' +
          '</div>' +
        '</div>'
      );
    });
```

- [ ] **Step 2: Set note input values via DOM after `innerHTML`**

After `container.innerHTML = [...sessionRows, ...manualRows].join('');`, add a block that sets note values via the DOM (avoids HTML-escaping issues with quotes/angle-brackets in note text):

```js
    container.innerHTML = [...sessionRows, ...manualRows].join('');

    // Set note values via DOM to avoid HTML-escaping issues
    sessions.forEach((s, si) => {
      const input = container.querySelector('.sess-note[data-ridx="' + i + '"][data-sidx="' + si + '"]');
      if (input) input.value = s.note || '';
    });
```

- [ ] **Step 3: Update the `sess-toggle` click handler to sync both badge buttons**

Find the existing toggle handler block:

```js
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
```

Replace with (key change: update ALL buttons with matching ridx/sidx, not just the one clicked):

```js
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
          const newCls = 'sess-toggle px-2 py-0.5 rounded text-xs ' +
            (updated.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400');
          const newLabel = updated.is_work ? 'Work' : 'Non-work';
          container.querySelectorAll('.sess-toggle[data-ridx="' + ri + '"][data-sidx="' + si + '"]').forEach(b => {
            b.textContent = newLabel;
            b.className = newCls;
          });
          const daily = await api.getDailySummary(60);
          renderChart(daily);
        } catch (err) {
          console.error('Toggle error:', err);
        }
      });
    });
```

- [ ] **Step 4: Add note input handlers**

After the `sess-toggle` handler block (and before `expandRow.classList.remove('hidden')`), add:

```js
    container.querySelectorAll('.sess-note').forEach(input => {
      const si = parseInt(input.dataset.sidx);
      const session = sessions[si]; // same sorted array used to render the rows
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
```

- [ ] **Step 5: Commit**

```bash
git add server/static/js/daily.js
git commit -m "feat: add note editing and responsive badge layout to daily view"
```

---

### Task 2: Update `dashboard.js` — responsive session rows

**Files:**
- Modify: `server/static/js/dashboard.js` (function `renderTodaySessions`, lines ~99–115)

The dashboard already has note editing. This task only changes the HTML structure to give the badge a fixed row on mobile.

- [ ] **Step 1: Replace the session row HTML template in `renderTodaySessions()`**

Find this block in `server/static/js/dashboard.js`:

```js
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
```

Replace with:

```js
      const badgeLabel = s.is_work ? 'Work' : 'Non-work';
      return (
        '<div class="border-t border-slate-700 px-4 pt-3 pb-3">' +
          '<div class="flex items-center gap-3 text-sm">' +
            '<span class="text-slate-300 tabular-nums shrink-0">' + start + ' – ' + end + '</span>' +
            '<span class="text-teal-400 font-medium shrink-0">' + fmtH(s.duration_hours) + '</span>' +
            '<span class="text-slate-500 text-xs shrink-0">' + s.computer + '</span>' +
            '<button class="ds-work-toggle ml-auto text-xs px-2 py-0.5 rounded hidden sm:inline-flex ' + workCls + '" data-idx="' + idx + '">' +
              badgeLabel +
            '</button>' +
          '</div>' +
          '<div class="mt-1.5 sm:hidden">' +
            '<button class="ds-work-toggle text-xs px-2 py-0.5 rounded ' + workCls + '" data-idx="' + idx + '">' +
              badgeLabel +
            '</button>' +
          '</div>' +
          '<div class="mt-1.5">' +
            '<input class="ds-note bg-transparent text-slate-400 text-xs w-full placeholder-slate-600 outline-none border-b border-transparent focus:border-slate-500 transition-colors" ' +
              'data-idx="' + idx + '" placeholder="Add note…">' +
          '</div>' +
        '</div>'
      );
```

Note: `workCls` is already defined as `s.is_work ? 'bg-teal-900 text-teal-300' : 'bg-slate-700 text-slate-400'` just above this block — no change needed there.

The existing `ds-work-toggle` click handler calls `Dashboard.load()` which re-renders the whole list, so both badge buttons update automatically. No handler changes needed.

- [ ] **Step 2: Commit**

```bash
git add server/static/js/dashboard.js
git commit -m "feat: fix badge wrapping on mobile in dashboard session rows"
```

---

### Task 3: Manual verification

**Files:** none (read-only verification)

- [ ] **Step 1: Start the server**

```bash
cd /home/alan/projects/personal/worktime-tracker
uvicorn server.main:app --reload
```

- [ ] **Step 2: Verify daily view — desktop**

Open `http://localhost:8000` → Daily tab. Expand today's row.

Expected:
- Each session row has: time–end | duration | computer | badge (right-aligned) on one line
- Note input below with `Add note…` placeholder
- Type a note, press Enter → note saves silently, no page reload
- Click Work/Non-work badge → toggles correctly on both desktop and mobile badge

- [ ] **Step 3: Verify daily view — mobile**

Resize browser to < 640px (or use DevTools mobile emulation).

Expected:
- Row 1: time range, duration, computer
- Row 2: Work/Non-work badge (always on its own line — no mid-row wrapping)
- Row 3: note input
- Toggling badge works; note saves on blur

- [ ] **Step 4: Verify dashboard — mobile**

Switch to Dashboard tab, resize to < 640px.

Expected:
- Same 3-row structure for today's sessions
- Badge always on row 2, note always on row 3
- Toggle and note save still work

- [ ] **Step 5: Verify note persistence**

Add a note to a session, reload the page, expand the day → note should still be there.
