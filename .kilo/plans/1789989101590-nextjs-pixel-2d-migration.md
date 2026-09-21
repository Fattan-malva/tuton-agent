# Next.js Frontend Migration - Pixel 2D RPG Cozy Theme

## Current State

- **Backend**: Flask (`server.py`) — unchanged, serves API at `/api/*` and static frontend from `frontend/`
- **Existing Next.js app**: `/home/ubuntu/automation/tuton-agent/web/`
  - Next.js 15.5.3, React 19, Tailwind CSS 4.1.5, TypeScript
  - App Router (`src/app/page.tsx`, `layout.tsx`, `globals.css`)
  - 6 placeholder components: Login, Navigation, Status, Results, Run, Settings
  - Static export configured (`output: "export"`)
  - **Built output** already deployed to `/home/ubuntu/automation/tuton-agent/frontend/` (`_next/`, `index.html`, `404.html`)
- **Original HTML frontend**: `/home/ubuntu/automation/tuton-agent/frontend/index.html` (replaced by Next.js build)

## What Is Broken / Incomplete

1. **Components are placeholders** — no real API integration, no live terminal, no cronjob form, no download/delete
2. **Pixel 2D RPG theme is not implemented** — only basic dark CSS variables, no pixel-art aesthetic
3. **API client points to `http://localhost:8000`** — wrong; should use relative paths since Flask serves the built app
4. **No tab/routing system** — original HTML had 4 tabs (Status, Result, Run, Settings) + login overlay
5. **No login/logout flow** — Login component simulates login locally, does not call `/api/login`
6. **Live process output missing** — no polling of `/api/run/output` or `/api/run/status`
7. **Cronjob form missing** — no schedule enable/day/time UI
8. **Results download/delete missing** — no `/api/download` or DELETE endpoints wired up
9. **Deployment path unclear** — need to ensure `next build` output ends up in `frontend/` for Flask to serve

## Target State

- Fully functional Next.js frontend at `https://tuton.mallvaa.xyz/`
- Dominant black + pixel 2D cozy RPG theme
- All original backend features preserved and wired up
- Zero changes to `server.py`, `config.py`, `main.py`, `moodle/`, `generator/`

## Plan

### Phase 1 — Fix Foundation

1. **Fix API client base URL**
   - Change `api-client.ts` baseUrl from `http://localhost:8000` to `""` (relative)
   - Add missing endpoints: `/api/courses`, `/api/courses/<id>/sections`, `/api/courses/<id>/activities`, `/api/run`, `/api/run/output`, `/api/run/status`, `/api/run/stop`, `/api/schedule`, `/api/login`

2. **Fix types**
   - Update `types.ts` to match actual backend response shapes:
     - `StatusItem`: `key`, `status`, `matkul`, `sesi`, `kind`, `index`, `desc`, `outputs[]`
     - `ResultItem`: course grouping, file metadata (`name`, `path`, `size`, `modified`, `kind`, `index`, `sesi`)
     - Add `Course`, `Section`, `Activity`, `Schedule` types

3. **Add app-level state/hooks**
   - Create `web/src/hooks/useTutonAuth.ts` — login state, localStorage `tuton_logged_in`, logout
   - Create `web/src/hooks/useRunPolling.ts` — poll `/api/run/output` + `/api/run/status` every 1s, parse progress

### Phase 2 — Implement Components (Pixel 2D RPG Cozy Theme)

4. **Design system — pixel 2D cozy RPG**
   - Update `globals.css` with:
     - Pixel font stack (e.g., `'Press Start 2P'` or `'Silkscreen'` for headings, `'Inter'` for body)
     - `image-rendering: pixelated`
     - 2px hard borders (no soft shadows)
     - 8px grid spacing
     - Dark dominant palette: `#0a0f1e` base, `#1a2332` cards, `#6366f1` accent (indigo/purple glow)
     - Pixel-art decorative elements (scanlines, grid backgrounds, CRT vignette)
   - Add Google Fonts for pixel font in `layout.tsx`

5. **Login component**
   - Replace simulated login with real `POST /api/login`
   - Username/password fields matching original HTML
   - On success: set localStorage, show app view
   - Pixel art styling: chunky borders, pixel icon, dark bg with subtle grid

6. **Navigation component**
   - Tab-based nav: Status Pekerjaan, Result, Run Agent, Settings
   - Active state with pixel-art underline/glow
   - Mobile hamburger menu
   - User footer with logout button

7. **Status component**
   - Stats cards (Done / Failed / Pending) from `/api/status`
   - Table with columns: Status, Mata Kuliah, Sesi, Deskripsi
   - Status badges with pixel-art colors (green=done, red=failed, yellow=pending)

8. **Results component**
   - Course cards grid from `/api/results`
   - Per-course file list with download button (`/api/download/<path>`)
   - Delete docx button (`DELETE /api/results/<path>`)
   - Delete whole course button (`DELETE /api/courses/<folder>`)
   - Pixel-art card styling with hard borders

9. **Run Agent component**
   - Left panel: course dropdown (`/api/courses`), sesi input, --force checkbox, cronjob form
   - Right panel: terminal with live output (poll `/api/run/output`)
   - Progress bar parsing log markers
   - Start/Stop buttons (`POST /api/run`, `POST /api/run/stop`)
   - Cronjob: enable toggle, day select, time input, next-run display (`GET/POST /api/schedule`)
   - Terminal styling: dark bg, pixel-font monospace, scanline overlay, colored log lines

10. **Settings component**
    - Form sections: Data Mahasiswa (NAMA, NIM, PRODI), Kredensial Moodle (cookie, URL), Model Configuration (OPENCODE_MODEL)
    - Save to `POST /api/config`
    - Load from `GET /api/config` on mount

### Phase 3 — Page Layout & Routing

11. **Update `page.tsx`**
    - Conditional render: if not logged in → `<Login />`, else → main app
    - Main app: `<Navigation />` + tab content area (client-side tab switching, no route changes needed)
    - Pass active tab state to Navigation

12. **Update `layout.tsx`**
    - Add Google Fonts link for pixel font
    - Add metadata

### Phase 4 — Build & Deploy

13. **Build Next.js**
    - Run `next build` in `web/`
    - Verify output in `web/out/` (or `.next/` depending on config)

14. **Deploy built files**
    - Copy `web/out/` contents to `frontend/` (preserving `_next/` and `index.html`)
    - Or configure Flask to serve from `web/out/` directly (modify `static_folder` in `server.py`)

15. **Validate**
    - Run Flask server, visit `http://localhost:5000`
    - Test login, tabs, API calls, terminal output, download/delete
    - Verify pixel 2D theme renders correctly
    - Confirm `https://tuton.mallvaa.xyz/` is accessible via reverse proxy / domain config

## Key Decisions Needed

1. **Pixel font choice** — Recommend: `'Press Start 2P'` (Google Fonts) for headings + `'Silkscreen'` as fallback, `'Inter'` for body text
2. **Tab routing** — Recommend: client-side tab switching within single page (matches original HTML behavior, no route changes)
3. **Deployment path** — Recommend: copy `web/out/` → `frontend/` after each build, OR update Flask `static_folder` to point to `web/out/`
4. **Terminal polling** — Recommend: `useEffect` with `setInterval` 1s, cleanup on unmount

## Risks

- **Build output mismatch**: Next.js static export filenames change per build; Flask must serve the latest `frontend/` contents
- **CORS / relative paths**: API client must use relative URLs; Flask and Next.js must be on same origin
- **Large terminal output**: Polling every 1s with many lines may cause performance issues; consider limiting buffer size
- **Pixel font loading**: Google Fonts may flash; preload in `layout.tsx`
