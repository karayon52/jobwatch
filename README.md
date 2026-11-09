# JobWatch on GitHub

Follow companies' job pages with **nothing running on your own device**.

- **GitHub Actions** checks every company in `companies.yml` about every 10 minutes, in GitHub's cloud.
- Results are saved as files in this repo (`data/`): an **inbox of notifications**, plus every open job per company.
- A **GitHub Pages** website shows the inbox. Open or refresh it any time to see what's new.

## Set up (about 5 minutes, all in your browser)

1. **Create the repo.** On github.com choose *New repository*, name it (for example `jobwatch`), set it to **Public**, then upload every file from this folder. Keep the folder structure and include the hidden `.github` folder.
   - Why public: Actions minutes are unlimited and free for public repos, and the free Pages site works. See "Private repo" below if you need it private.
2. **Allow the bot to save results.** *Settings → Actions → General → Workflow permissions → Read and write permissions → Save.*
3. **Turn on the website.** *Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main`, folder `/docs` → Save.* After a minute your site is at `https://YOUR-USERNAME.github.io/REPO-NAME/`.
4. **Run the first check.** *Actions tab → collect → Run workflow.* (If GitHub shows a button to enable workflows, click it.)
5. **Open your site.** The first check saves each company's current jobs quietly, so the inbox fills as new postings appear. **Open jobs** shows everything that's open right now.

## Choose your companies

Open `companies.yml` on github.com, click the pencil, edit, and commit. A check starts automatically. Per company you can filter by keywords and locations (see the comments in the file). Supported: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, RSS feeds, and simple static careers pages.

## Reading the inbox

- A blue dot marks alerts you haven't seen; the tab title shows the count. **Mark all read** clears them (stored in your browser).
- Search, filter by company, or show only new / only updated postings.
- The **Companies** tab shows each source's health and the exact error if one can't be read.
- The website can't start a check itself (that would need a secret key in your browser). Use **Run a check now** on the Companies tab for an immediate one.

## Optional: also get a phone push

The inbox is enough on its own, but you can add instant pushes with *Settings → Secrets and variables → Actions → New repository secret*:

| Secret | Value |
|---|---|
| `NTFY_TOPIC` | A hard-to-guess name, e.g. `jobs-x7k2q9`. Install the ntfy app and subscribe to it. |
| `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` | From @BotFather, and your chat ID (message the bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates`). |

## Good to know

- **Timing:** GitHub treats the 10-minute schedule as best effort and often runs a few minutes late. The page tells you when the last check ran.
- **Public data:** in a public repo, your watchlist and the saved postings are visible to anyone. The postings are already public on the companies' sites.
- **Private repo:** Pages needs a paid GitHub plan, and Actions minutes are limited (2,000 a month free, about 1 minute per run). To stay in the free allowance change the cron in `.github/workflows/collect.yml` to `*/30 * * * *`, and read the inbox from `data/notifications.json` in the repo.
- **Idle repos:** GitHub pauses schedules after 60 days without activity. A small built-in job keeps the repo active; if schedules ever stop, click *Enable workflow* on the Actions tab.
- **JavaScript-only careers pages** can't be read. Use the company's Greenhouse/Lever/Ashby link instead.

## How it works

`collector/run.py` fetches each company, compares with the saved state in `data/companies/`, and appends alerts to `data/notifications.json`. The workflow commits only when something changed. Reposts under a new ID, empty fetches, and duplicate alerts are filtered out, and each company's errors are isolated so one broken site never blocks the others.

Run the tests locally with `pip install -r requirements-dev.txt && pytest`.
