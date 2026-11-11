# Deploying to Lightsail

## How it works now (open on the static IP, auto-deploy)

- **Every push to `main` that changes bot code deploys.** Opening a PR only runs CI (typecheck, tests, build). When the PR is merged, the **Deploy** workflow tests and builds again, uploads the release to the server and restarts the bot. No manual step.
- **Research-only pushes skip the deploy** (since Nov 11): when nothing changed since the last deploy reaches the server (docs, python apart from the heat reader's files, tests, other workflows, research files the release does not bundle; the list is in `deploy/deploy-scope.ts`), the run's summary says `research-only: <files>; bot not restarted`. `[skip deploy]` in the message no longer skips a push that changes bot code: it deploys with a warning. Do not put `[skip ci]` on merges to `main`: it stops GitHub from starting any workflow, so a bot change merged with it gets no deploy of its own and ships with the next deploy, whose summary warns that it was batched. When the last deploy cannot be looked up (GitHub API error), the push deploys.
- The dashboard is at **http://54.145.7.203:3000/** (the Lightsail static IP). It opens without a login, unless you set a dashboard password (below).
- A bad release rolls itself back: if the service doesn't start, or the dashboard doesn't answer on port 3000 after the restart, the previous release is put back.
- Each release lives in `~/releases/<name>` on the server (the 5 newest are kept). `~/bot/current` points at the live one.
- Models, recordings and state are in `~/bot/data` and survive every deploy.

### Heat curve reader (beside the bot, runs while `HEAT_LANE=true`)

The heat lane's curve reader (`docs/HEAT_READER.md`) is a small Python service, `heat-reader`, that runs beside the bot from the release itself. Every release whose commit has them ships `python/heat_reader` and `python/oracle` (without their tests, fixtures, preregistration notes and markdown) and the oracle run's packs, `research/oracle_heat/latest/*.json` and `RUN` (not the league tables); the list is `HEAT_SHIP` in `deploy/deploy-scope.ts`, and a push that changes only those files deploys (the rest of `research/oracle_heat` never does). A commit without them ships nothing extra (`python/oracle` and the packs are on `main` since #328, the reader and its installer since #327). Their upload is part of the release's: if it fails, the run fails before activation and the bot keeps its release. After the bot is up and its dashboard answers, `deploy/activate.sh` runs the release's `deploy/heat_reader_install.sh` when it has one: with `HEAT_LANE=true` in `~/bot/bot.env` it builds the reader's venv (pip: minutes the first time, cut off after 15) and starts the reader, otherwise it stops it. It runs with the kernel's highest OOM score, so a pip build that runs the server out of memory is killed instead of the bot. It never fails a deploy and never rolls the bot back: when the reader cannot start, the deploy log says `heat reader: NOT running` with the reason, the reader is stopped and disabled (no reader from an earlier release keeps running beside the new bot), and the bot runs as before. `rollback.sh` makes the reader follow the release it rolls back to (stopped when that release has no reader). On this server the lane is switched on by the deploy itself: from a release that ships the installer, `deploy/ensure-env.sh` adds `HEAT_LANE=true` to a `bot.env` that has no `HEAT_LANE` line, and then `PLAN_RULES=true` when that line is missing too (the lane's positions are plan positions, and the bot refuses `HEAT_LANE=true` without it). A line already there is never changed, so `HEAT_LANE=false` keeps the lane and its reader off across deploys; live trading stays behind its own switch. After changing `HEAT_LANE`, run `bash ~/bot/current/deploy/heat_reader_install.sh`. The Server diagnostics workflow reports it under `== heat reader`.

### One-time setup (only if the old bot's repo secrets are not already in this repo)

1. **GitHub secrets** (repo Settings → Secrets and variables → Actions): `LIGHTSAIL_HOST` (`54.145.7.203`), `LIGHTSAIL_USERNAME` (`ubuntu`), `LIGHTSAIL_SSH_KEY` (the private key), and optionally `LIGHTSAIL_PORT`.
2. **Lightsail firewall:** in the instance's Networking tab, add a TCP rule for port 3000 (the previous bot already had it).
3. **Server needs** Node 22, and `ubuntu` must have passwordless `sudo` (the Lightsail default).
4. Merge the PR. The first deploy creates `~/bot/bot.env` for you, in **paper** mode, with the dashboard open (no login).

### Dashboard password (optional)

Without a password, anyone who can reach port 3000 can see the dashboard and use the kill switch. To add a login, use either of these:
- **From GitHub (no SSH):** add the repository secret `DASHBOARD_PASSWORD` (Settings → Secrets and variables → Actions). The next deploy writes it into `~/bot/bot.env`. Re-run the Deploy workflow from the Actions tab to apply it now.
- **On the server:** add `DASHBOARD_PASSWORD=...` to `~/bot/bot.env`, then `sudo systemctl restart kalshi-bot`.

To remove the login again, delete the secret *and* the line in `~/bot/bot.env`, then restart.

If the old bot is running under the same `kalshi-bot` service name, the first deploy replaces it. Its `~/bot/bot.env` and `~/bot/data` are kept, and the new bot starts with them. If `~/bot/current` is a real directory instead of a link, move it aside once (`mv ~/bot/current ~/bot/old-current`) before the first deploy.

### Everyday commands (on the server)

| What | Command |
|---|---|
| Logs | `journalctl -u kalshi-bot -f` |
| Status | `systemctl status kalshi-bot` |
| Roll back to the previous release | `bash ~/bot/current/deploy/rollback.sh` (research-only pushes leave it in place; the next push that changes bot code deploys `main`) |
| Change settings | edit `~/bot/bot.env`, then `sudo systemctl restart kalshi-bot` |
| Redeploy without a code change | Actions tab → Deploy → Run workflow |
| Deploy a tagged release | same, entering the tag (e.g. `v2.1.0`); it stays until a push changes bot code |
| Import history CSVs | `ssh ubuntu@54.145.7.203 mkdir -p ~/incoming`, `scp *.csv ubuntu@54.145.7.203:~/incoming/`, then `bash ~/bot/current/deploy/history.sh import ~/incoming` |
| Download / refresh history now | `bash ~/bot/current/deploy/history.sh binance` and `... coinbase` (the daily pipeline does this too) |
| One-off BTC.D / USDT.D history from TradingView | `bash ~/bot/current/deploy/history.sh tradingview` (needs `sudo apt install python3-venv git` once; docs/TA_NETWORK.md) |
| See stored history | `bash ~/bot/current/deploy/history.sh status` |
| Seed history shipped with the code | `deploy/seed/history/` (Yahoo daily BTC, ETH, SOL, XRP, DOGE back to 2016–2020); the daily pipeline imports it once. It only fills days Binance and Coinbase don't cover |
| Retrain the TA network now | `bash ~/bot/current/deploy/history.sh train` |

### Live trading is a separate switch

The deploy never changes `TRADING_MODE`. A new server starts in `paper`. Going live is done by hand in `~/bot/bot.env`.

Right before the switch, run the go-live checklist in the README ("Right before switching to live", under Modes): the kill switch, PLAY / STOP, the kill-switch override, each book's probation against the live limit, `LIVE_ALLOW_UNVALIDATED_MODEL`, the margin balance and the cash split.

### Connecting the prediction and perps APIs (live)

1. **Key:** in Kalshi's account settings, create an API key and download its private key. Copy the private key to the server (`scp key.pem ubuntu@54.145.7.203:~/.kalshi/private_key.pem`), then `chmod 600 ~/.kalshi/private_key.pem`. One key works for both the prediction API and the perps REST API (a separate perps key is optional).
2. **Edit `~/bot/bot.env`:**
   ```
   TRADING_MODE=live
   KALSHI_ENV=prod
   LIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK
   KALSHI_KEY_ID=<your key id>
   KALSHI_PRIVATE_KEY_PATH=/home/ubuntu/.kalshi/private_key.pem
   # Optional: trade binary contracts even though the model hasn't passed validation (your risk).
   LIVE_ALLOW_UNVALIDATED_MODEL=true
   # Optional: a separate perps key instead of the one above.
   # KALSHI_PERPS_KEY_ID=...
   # KALSHI_PERPS_PRIVATE_KEY_PATH=...
   ```
   The dashboard's LIVE switch (`POST /api/mode`) writes the first three lines and nothing else. Perps and tennis stay as configured and each needs its own switch: `PERP_TRADING=live` and `PERP_HEDGE=live` for real perps orders (a `paper` perps setting is off in live mode), `TENNIS_LIVE=true` for real tennis orders (without it tennis only tracks matches in live mode). Set `PERP_TRADING=live` / `PERP_HEDGE=live` only in a bot.env that already says `TRADING_MODE=live` (this edit, or after the LIVE switch, then restart): next to `TRADING_MODE=paper` they stop the bot from starting (exit code 2), and it stays down until bot.env is fixed. The dashboard's PAPER switch writes `TRADING_MODE=paper`, sets a `live` perps setting back to `paper` and writes `TENNIS_LIVE=false`. Both switches check bot.env as it is now and refuse, writing nothing, when the restart would not start; that includes LIVE with `LIVE_ALLOW_UNVALIDATED_MODEL=false`, an unvalidated model, a closed `kalshi` gate and no other live book (exit code 3).
3. **Restart and check:** `sudo systemctl restart kalshi-bot`, then `journalctl -u kalshi-bot -f`.
   - `GET /margin/enabled says margin trading is not enabled` means Kalshi hasn't switched perps on for the account yet (it is rolling out member by member). Perp orders are rejected until it is. The prediction side still trades.
   - Perps trade from the margin balance. Moving money from the event-contract balance to margin needs Kalshi's transfer, which isn't available through the API yet, so do it on the website.

**What stays on while live, whatever the settings:**
- the risk limits and the kill switch (the daily loss stops and the weekly pause halt live trading only with the kill-switch override off; it is ON by default, see the README checklist)
- the exchange's own status and maintenance schedule: no new entries while trading is paused, during maintenance, or in the 10 minutes before a scheduled window
- price-grid snapping (orders always land on the market's valid prices)
- reconciliation against the exchange
- for perps, the setup lanes size by risk per trade, at pilot size (`PERP_PILOT_MAX_NOTIONAL_USD`) while a lane isn't validated

## Making it more secure (later)

Each step is independent. Do as many as you like.

1. **Hide the dashboard from the internet.** In `~/bot/bot.env` set `BIND_HOST=127.0.0.1` and delete `ALLOW_NON_LOOPBACK_BIND=true`, restart. Reach it with `ssh -L 3000:127.0.0.1:3000 ubuntu@54.145.7.203`, then open http://127.0.0.1:3000/. Close port 3000 in the Lightsail firewall.
   - Alternative: keep it reachable but over HTTPS (below).
2. **Restrict SSH** to your own IP in the Lightsail firewall.
3. **Stop deploying on every push.** Set the repository **variable** `AUTO_DEPLOY` to `false`. Pushes then only run CI; deploys happen from Actions → Deploy → Run workflow with a release tag.
4. **Require approval for deploys.** Settings → Environments → `production` → Required reviewers. Every deploy (automatic or manual) then waits for a reviewer.
5. **Set a strong dashboard password** (`DASHBOARD_PASSWORD`, long and random, e.g. `openssl rand -hex 32`), see above.
6. **Use a dedicated deploy key.** Create a separate SSH key just for deploys, and replace `LIGHTSAIL_SSH_KEY`.

None of these needs a code change.

## HTTPS (set up by every deploy)

`deploy/https.sh` installs Caddy and puts the dashboard behind TLS at **https://54-145-7-203.sslip.io**
(the server's IP with dashes; sslip.io is a free DNS name that points at it). The certificate comes from
Let's Encrypt and renews itself; only TLS 1.2/1.3 is accepted, with HSTS. It costs a few MB of memory and
no noticeable CPU.

To turn it on:
1. Lightsail console -> the instance -> Networking -> IPv4 firewall: add **HTTPS (443)** and keep **HTTP (80)**
   (Let's Encrypt checks and the redirect to HTTPS use it).
2. Set `DASHBOARD_PASSWORD` (see above) and open the https address.
3. Once it works, delete the **3000** rule in the same firewall: plain http is then closed to the internet.

Options in `~/bot/bot.env`: `DASHBOARD_DOMAIN=bot.example.com` (a name you own, pointed at the server) instead
of sslip.io; `HTTPS=off` to skip Caddy entirely.
