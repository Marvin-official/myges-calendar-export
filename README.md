# MyGES → iPhone calendar

A GitHub Action fetches your MyGES schedule every 3 hours and publishes it as
an `.ics` file on GitHub Pages. Your iPhone subscribes to that URL and stays
in sync.

It uses the same API as the official MyGES app (`api.kordis.fr`), so it
doesn't break when the website's HTML changes.

## Setup

1. **Create a repository** and push these files (`myges_ics.py` and
   `.github/workflows/calendar.yml`). On a free GitHub plan, Pages needs a
   **public** repo. That's fine: your schedule and credentials are never
   committed. Only the deployed file exists, at a secret URL.

2. **Add 3 secrets** in *Settings → Secrets and variables → Actions → New
   repository secret*:

   | Name             | Value                                         |
   | ---------------- | --------------------------------------------- |
   | `MYGES_USERNAME` | your MyGES login                              |
   | `MYGES_PASSWORD` | your MyGES password                           |
   | `CALENDAR_TOKEN` | a long random string, e.g. from `openssl rand -hex 16` |

3. **Turn on Pages**: *Settings → Pages → Build and deployment → Source:
   GitHub Actions*.

4. **Run it once**: *Actions → Update MyGES calendar → Run workflow*.

5. **Subscribe on iPhone**: *Settings → Apps → Calendar → Calendar Accounts →
   Add Account → Other → Add Subscribed Calendar*, and enter:

   ```
   https://<your-github-username>.github.io/<repo-name>/<CALENDAR_TOKEN>.ics
   ```

   (On older iOS: *Settings → Calendar → Accounts → Add Account → Other*.)
   iOS refreshes subscribed calendars on its own; you can set how often under
   *Calendar → Fetch New Data*.

## Run locally

```bash
MYGES_USERNAME=... MYGES_PASSWORD=... python3 myges_ics.py --out myges.ics
```

Options: `--weeks-back` (default 4), `--weeks-ahead` (default 20), `--name`
(calendar name, default `MyGES`).

## Notes

- Anyone with the URL can read your schedule, so keep `CALENDAR_TOKEN` private.
  To revoke a link, change the secret and re-run the workflow.
- GitHub pauses scheduled workflows after 60 days without commits in the repo.
  It emails you first; re-enable it from the Actions tab or push any commit.
- If the login or the API call fails, the run fails and the last published
  calendar stays online.
