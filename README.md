# ⚽ Family WC 2026 Prediction Game

A self-hosted web app for family members to predict 2026 FIFA World Cup match outcomes and earn points. Runs on your homelab via Docker Compose.

## Features

- 8 predefined family accounts — no self-registration
- First login sets your own password; subsequent logins use it
- Predict Home win / Draw / Away win for each match
- Live scoreboard, grouped by date
- 5 points for a correct prediction, 0 for wrong
- Auto-syncs matches and results from football-data.org every 30 minutes
- Admin panel for manual sync and match overrides

## Prerequisites

- Docker and Docker Compose installed on your homelab
- A free API key from [football-data.org](https://www.football-data.org/client/register)

## Setup

### 1. Get your API key

Register for a free account at <https://www.football-data.org/client/register>.  
Your API key (Tier 1, free) gives access to WC 2026 match data.

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```
FOOTBALL_API_KEY=your_actual_key_here
SECRET_KEY=some-long-random-string
PORT=8000
```

Generate a strong `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start the app

```bash
docker compose up -d
```

The app will:
1. Create the SQLite database at `./data/db.sqlite`
2. Seed the 8 predefined user accounts
3. Run an initial match sync from football-data.org
4. Start the background scheduler (syncs every 30 minutes)

Open <http://your-homelab-ip:8000> in your browser.

### 4. First login

1. Go to <http://your-homelab-ip:8000>
2. Select your name from the dropdown
3. Leave the password field blank and click **Sign in**
4. You'll be prompted to set your password — it applies to all future logins

## Usage

| Page | URL | Who |
|------|-----|-----|
| Dashboard | `/dashboard` | Everyone |
| Leaderboard | `/leaderboard` | Everyone |
| Admin | `/admin` | Violin only |

**Making a prediction:** click a radio button (Home / Draw / Away) on the Dashboard. The form auto-submits. You can change your pick any time until kick-off.

**Admin sync:** go to `/admin` and click **Sync Now** to pull the latest results immediately.

## Updating / stopping

```bash
# Pull latest (if you rebuild)
docker compose build && docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The database is stored in `./data/db.sqlite` (a Docker bind mount) and survives restarts.

## Architecture

```
soccer-predictor/
├── docker-compose.yml
├── .env                   ← your config (not committed)
├── .env.example
├── data/                  ← SQLite DB (auto-created)
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py            ← FastAPI app + scheduler + startup
    ├── database.py        ← SQLAlchemy engine + session
    ├── models.py          ← User, Match, Prediction ORM models
    ├── auth.py            ← bcrypt hashing + JWT cookie auth
    ├── football_api.py    ← API client + sync/points logic
    ├── routers/
    │   ├── auth.py        ← /login, /set-password, /logout
    │   ├── matches.py     ← /, /dashboard
    │   ├── predictions.py ← POST /predictions
    │   └── admin.py       ← /leaderboard, /admin, /admin/sync, /admin/match
    └── templates/
        ├── base.html
        ├── login.html
        ├── set_password.html
        ├── dashboard.html
        ├── leaderboard.html
        └── admin.html
```

## Scoring

| Outcome | Points |
|---------|--------|
| Correct winner or draw | **5 pts** |
| Wrong prediction | **0 pts** |

Points are awarded automatically when a match status becomes `FINISHED`.

## Troubleshooting

**No matches showing up**
- Check your `FOOTBALL_API_KEY` in `.env`
- Visit `/admin` as Violin and click **Sync Now**
- Check logs: `docker compose logs -f`

**"Invalid API key" in logs**
- Ensure the key is correct and the `.env` file was reloaded: `docker compose up -d`

**Port conflict**
- Change `PORT=8000` in `.env` to another port
