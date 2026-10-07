from app import app, seed_database

with app.app_context():
    seed_database()
    print("Database initialized and seeded.")
