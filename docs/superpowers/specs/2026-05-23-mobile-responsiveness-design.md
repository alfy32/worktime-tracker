# Mobile Responsiveness Design

**Date:** 2026-05-23

## Problem

The worktime tracker UI was built desktop-first. On phones the navigation overflows off the right edge and the three data tables (Daily, Weekly, Log) are unreadably wide.

## Design

### Navigation

Responsive hamburger nav: below `md` (768px), the tab bar is replaced by a hamburger button that opens a full-width dropdown. Above `md`, tabs show normally. Same `tab-btn` class on both sets so active-state styling works identically. Closing the menu happens automatically on navigation.

### Tables

All three tables wrapped in `overflow-x-auto` as a safety net. Columns appear progressively as screen width increases:

| Table | Always | sm (640px+) | md (768px+) |
|---|---|---|---|
| Daily | Date, Hours | Sessions | Longest Break |
| Weekly | Week of, Total Hours | vs 40h | Avg / Day |
| Log | Login, Duration, Work? | Computer, Note | — |

### Cards & Typography

- Hero card: `p-8` → `p-4 sm:p-8`
- Hero number: `text-5xl` → `text-3xl sm:text-5xl`
- Hero subtitle: `text-lg` → `text-base sm:text-lg`
- Week hours: `text-3xl` → `text-2xl sm:text-3xl`

### Session Detail Rows

Removed hardcoded `w-36`, `w-16` flex widths from `daily.js` expand rows. Items now flow naturally with the existing `flex-wrap`.

### Charts

Replaced hardcoded `style="height:Npx"` with responsive Tailwind height classes (`h-36 sm:h-44 md:h-[Npx]`). Chart.js already uses `responsive: true`.

### Safe Area

Added `padding-bottom: env(safe-area-inset-bottom)` to `body` for phones with home bars.
