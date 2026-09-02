"""WSGI entry point for production deployment."""

from app import create_app

app = create_app("app.config.ProductionConfig")

if __name__ == "__main__":
    app.run()
