import click

from app import db
from app.models import User


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(name, email, password):
        """Create an admin user."""
        email = email.strip().lower()
        existing = db.session.scalar(db.select(User).filter_by(email=email))
        if existing:
            click.echo("A user with this email already exists.")
            return

        user = User(name=name.strip(), email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin created: {email}")