# Ava Anthony

First UI sketch for the high-school Sunday school team at **كنيسة العذراء مريم ايتاي البارود**.

## Product scenarios

### 1. Sunday check-in
1. A servant opens the Attendance view on a phone, tablet, or laptop.
2. The class roster appears with quick Present / Late / Absent actions.
3. The app saves the attendance record and optionally gives the weekly attendance points.
4. A student can see their current streak and encouragement message.

### 2. Notice the good
1. A servant selects a student.
2. They choose a reason such as “brought a friend”, “memorized the verse”, “helped the class”, or “consistent attendance”.
3. Ava Anthony adds points and records a short note.
4. The student's progress updates on their profile and in the group activity feed.

### 3. Rewards and celebration
1. Servants or admins create rewards with a points cost.
2. Students browse the available rewards and request one when they have enough points.
3. A servant approves the request and marks it as delivered.
4. The app keeps a simple history so rewards stay fair and visible.

### 4. Monthly follow-up
1. A servant sees attendance trends, students who missed two Sundays, and current streaks.
2. The team uses this as a pastoral follow-up list—not as a public ranking.
3. A servant records a private follow-up note or marks the student as contacted.

### 5. Church administration
1. A church admin manages classes, servants, students, point reasons, and reward catalog entries.
2. Data is separated by church and class so access is limited to the right people.
3. A monthly export can be created for backup and review.

## Suggested free deployment scenarios

### Scenario A — prototype / demo

Use **GitHub Pages** for this static `index.html`. It is the simplest path and is enough while the app uses demo data or local browser storage. The repository should be public on GitHub Free, and Pages publishes the HTML/CSS/JavaScript from the repository.

### Scenario B — first real pilot

Use **Cloudflare Pages** for the frontend and **Supabase** for authentication and data. Cloudflare Pages can connect directly to the Git repository and has a free tier; Supabase's free plan provides a small Postgres database, authentication, storage, and row-level security. This is the recommended starting architecture for one church.

### Scenario C — React/Next.js production-shaped version

Use **Vercel Hobby** for the web app and Supabase for data/authentication. It is convenient for preview deployments and server-rendered features, but the current Hobby plan is intended for personal, non-commercial use, so confirm that its terms fit the church's use before relying on it long-term.

### Scenario D — keep everything in one ecosystem

Use **Cloudflare Pages + Pages Functions + D1**. This keeps the frontend, small server-side endpoints, and database in one provider. It is attractive when we want to avoid a second service, but it requires more backend work than Supabase for authentication and admin permissions.

## Recommended path

Start with Scenario A for the visual prototype, then move to Scenario B for the first live pilot. Keep the UI as a responsive web app, with role-based access for `admin`, `servant`, and `student`. Before using real student data, add authentication, private access, backups, and a clear data-retention policy.
