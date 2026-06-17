# Kramp Market Intelligence Dashboard — Standalone

This folder contains a self-contained snapshot of the dashboard that runs in any modern browser. All data is embedded inline; no backend required.

## File contents
- `index.html` — full dashboard (Barlow font, white + Kramp red theme, all 5 pages)
- `*.json` — original data snapshots (kept for reference; not loaded by index.html)

## Local preview
```bash
cd kramp-dashboard-deploy
python3 -m http.server 8080
# open http://localhost:8080
```

## Deploy options

### 1. GitHub Pages (free, permanent URL)
```bash
cd kramp-dashboard-deploy
git init -b main
git add .
git commit -m "Kramp MI dashboard snapshot"
gh repo create kramp-mi-dashboard --public --source=. --push
gh api -X POST repos/:owner/kramp-mi-dashboard/pages -f source[branch]=main -f source[path]=/
# Live at: https://<your-user>.github.io/kramp-mi-dashboard/
```

### 2. Netlify Drop (drag & drop, no account needed for preview)
1. Go to https://app.netlify.com/drop
2. Drag the `kramp-dashboard-deploy` folder onto the page
3. Get an instant URL like `https://random-name.netlify.app`

### 3. Vercel (one command, requires Vercel account)
```bash
npx vercel --prod kramp-dashboard-deploy
```

### 4. Anywhere static — just upload index.html
S3 + CloudFront, Cloudflare Pages, Surge.sh, Render, Fly.io, internal Kramp web server, etc.

## Data freshness
Data is a **snapshot** captured on 2026-06-17. To refresh, re-run the build script
from the OpenCode session that owns the source artifact.
