import logging
import os

from flask import Flask, jsonify, render_template

from app.api.health import health_blueprint


def create_app(test_config=None):
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(level=os.environ.get("AGRION_LOG_LEVEL", "INFO").upper())
    app.register_blueprint(health_blueprint)

    @app.get("/")
    def index():
        return render_template("index.html", maptiler_api_key=os.environ.get("MAPTILER_API_KEY", ""))

    @app.errorhandler(404)
    def not_found(error):
        return jsonify(error="not_found"), 404

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Unhandled server error")
        return jsonify(error="internal_server_error"), 500

    return app
