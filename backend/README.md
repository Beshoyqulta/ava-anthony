# Ava Anthony Python API

This backend provides the first real API for the Ava Anthony Sunday-school app.

## Local setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py
python app.py
```

The API runs at `http://localhost:5000`.

Important: change `JWT_SECRET` in `.env` before using real data.

## Main endpoints

- `POST /api/auth/signup` — create a student or admin account
- `POST /api/auth/login` — receive a JWT token
- `POST /api/auth/forgot-password` — reset a password using phone and birthday until SMS OTP is connected
- `GET /api/me` — current account
- `GET /api/badges` — active badge catalog
- `POST /api/badges` — admin/super-admin badge creation
- `POST /api/qr-sessions` — open a live QR session for a catalog طايو (admin)
- `POST /api/qr-sessions/<token>/close` — close the live QR session (admin)
- `POST /api/badges/redeem` — student redemption using the active session token
- `GET /api/students` — admin/super-admin student list
- `POST /api/students/<id>/points` — admin awards a selected badge (and its points); legacy direct points payloads are also supported
- `GET /api/students/<id>/points` — admin point-award history
- `DELETE /api/students/<id>/badges/<award_id>` — admin removes an awarded badge and its points
- `GET /api/admins` — super-admin admin list
- `GET /api/leaderboard` — leaderboard
- `POST /api/attendance` — admin attendance recording
- `GET /api/attendance` — attendance records

Send the token returned by login as:

```text
Authorization: Bearer YOUR_TOKEN
```

SQLite is used locally by default. For deployment, set `DATABASE_URL` to a PostgreSQL connection string.

On startup, older positive manual point records are converted into badge awards without double-counting their points. Negative adjustments remain point adjustments.

## Free deployment path

Recommended pilot setup:

1. Push the repository to GitHub.
2. Create a PostgreSQL project in Supabase and copy its connection string from the Connect menu.
3. In Render, create a new Web Service connected to the GitHub repository.
4. Set the service Root Directory to `backend`.
5. Set Build Command to `pip install -r requirements.txt`.
6. Set Start Command to `gunicorn app:app`.
7. Add these Render environment variables:

```text
DATABASE_URL=your-supabase-postgres-connection-string
JWT_SECRET=a-long-random-secret
FRONTEND_ORIGIN=https://your-github-pages-domain
```

8. Deploy once. On startup the API creates the tables and seeds the eight default الطايوهات.
9. Update `API_BASE` in the frontend from `http://localhost:5000/api` to your Render API URL followed by `/api`.
10. Publish the frontend files on GitHub Pages or as a Render Static Site.

For a real church deployment, use PostgreSQL rather than SQLite. Render free services can sleep after inactivity, so the first request after a quiet period may be slow; the free tier is best treated as a pilot environment.
