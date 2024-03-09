"""
stockcount app initialization
"""

from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mailman import Mail
from flask_sqlalchemy import SQLAlchemy

from stockcount.config import Config

mail = Mail()
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = "main.home"
login_manager.login_message_category = "info"


def register_extensions(app):
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)


def register_blueprints(app):
    for module_name in ("users", "counts", "main", "errors"):
        module = __import__(f"stockcount.{module_name}.routes", fromlist=[module_name])
        app.register_blueprint(getattr(module, module_name))


def configure_database(app):
    with app.app_context():
        db.reflect()

    @app.teardown_request
    def shutdown_session(exception=None):
        db.session.remove()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(Config)

    register_extensions(app)
    register_blueprints(app)
    configure_database(app)

    return app
