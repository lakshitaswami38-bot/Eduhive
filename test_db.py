from app import create_app, db

app = create_app()

with app.app_context():
    db.session.execute(db.text("SELECT 1"))
    print("MySQL connected!")