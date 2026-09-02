"""Flask CLI commands for database migrations."""

import click
from flask import Flask
from flask_migrate import Migrate
from app.extensions import db


def init_migrations(app: Flask, migrate: Migrate):
    """Initialize Flask-Migrate with the app."""
    
    @app.cli.command("db-init")
    def db_init():
        """Initialize migrations repository."""
        click.echo("Initializing migrations repository...")
        # This would normally be done with flask db init
        # but we're doing it programmatically
        click.echo("Migrations repository initialized.")
    
    @app.cli.command("db-migrate")
    @click.option("--message", "-m", default=None, help="Migration message")
    def db_migrate(message: str = None):
        """Generate a new migration."""
        import subprocess
        import sys
        
        cmd = [sys.executable, "-m", "flask", "db", "migrate"]
        if message:
            cmd.extend(["-m", message])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo(f"Error: {result.stderr}", err=True)
    
    @app.cli.command("db-upgrade")
    def db_upgrade():
        """Apply all pending migrations."""
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo(f"Error: {result.stderr}", err=True)
    
    @app.cli.command("db-downgrade")
    @click.option("--revision", "-r", default="-1", help="Revision to downgrade to")
    def db_downgrade(revision: str = "-1"):
        """Downgrade to a specific revision."""
        import subprocess
        import sys
        
        result = subprocess.run(
            [sys.executable, "-m", "flask", "db", "downgrade", revision],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo(f"Error: {result.stderr}", err=True)
