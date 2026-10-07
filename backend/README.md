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

Important: change `SUPER_ADMIN_PASSWORD` and `JWT_SECRET` in `.env` before using real data.

## Main endpoints

- `POST /api/auth/signup` — create a student or pending admin account
- `POST /api/auth/login` — receive a JWT token
- `GET /api/me` — current account
- `GET /api/badges` — active badge catalog
- `POST /api/badges` — admin/super-admin badge creation
- `POST /api/badges/redeem` — student QR redemption
- `GET /api/students` — admin/super-admin student list
- `GET /api/admins` — super-admin admin list
- `POST /api/admins/<id>/approve` — super-admin approval
- `GET /api/leaderboard` — leaderboard
- `POST /api/attendance` — admin attendance recording
- `GET /api/attendance` — attendance records

Send the token returned by login as:

```text
Authorization: Bearer YOUR_TOKEN
```

SQLite is used locally by default. For deployment, set `DATABASE_URL` to a PostgreSQL connection string.

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
SUPER_ADMIN_PHONE=201xxxxxxxxx
SUPER_ADMIN_PASSWORD=a-strong-password
SUPER_ADMIN_NAME=اسم السوبر خادم
```

8. Deploy once. On startup the API creates the tables and seeds the super-admin account and the eight default الطايوهات.
9. Update `API_BASE` in the frontend from `http://localhost:5000/api` to your Render API URL followed by `/api`.
10. Publish the frontend files on GitHub Pages or as a Render Static Site.

For a real church deployment, use PostgreSQL rather than SQLite. Render free services can sleep after inactivity, so the first request after a quiet period may be slow; the free tier is best treated as a pilot environment.
