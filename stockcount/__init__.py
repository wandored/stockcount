"""
stockcount app initialization
"""

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from importlib import import_module

from stockcount.config import Config
from stockcount.models import db, mail, security, user_datastore


def register_extensions(app):
    db.init_app(app)
    mail.init_app(app)
    security.init_app(app, user_datastore)


def register_blueprints(app):
    for module_name in ("authentication", "counts", "main"):
        module = import_module("stockcount.{}.routes".format(module_name))
        app.register_blueprint(module.blueprint)


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
