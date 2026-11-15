import logging
import os

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api.health import health_blueprint
from app.api.discovery import discovery_blueprint, register_socket
from app.api.assistant import assistant_blueprint
from app.api.dashboard import dashboard_blueprint
from app.api.stations import stations_blueprint
from app.api.planning import planning_blueprint


def create_app(test_config=None):
    app = Flask(__name__)
    # Only the local Nginx proxy can reach the published application port.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(level=os.environ.get("AGRION_LOG_LEVEL", "INFO").upper())
    app.register_blueprint(health_blueprint)
    app.register_blueprint(discovery_blueprint)
    app.register_blueprint(assistant_blueprint)
    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(stations_blueprint)
    app.register_blueprint(planning_blueprint)
    register_socket(app)

    @app.after_request
    def discovery_no_cache(response):
        if request.path.startswith(("/api/interview/", "/api/assistant/", "/api/dashboard/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        def seconds(name, default):
            try:
                value = int(os.environ.get(name, default))
                return value if 1 <= value <= 3600 else default
            except ValueError:
                return default

        return render_template("index.html", maptiler_api_key=os.environ.get("MAPTILER_API_KEY", ""), interview_limits={
            "normal": seconds("AGRION_INTERVIEW_NORMAL_SECONDS", 180),
            "grace": seconds("AGRION_INTERVIEW_GRACE_SECONDS", 120),
            "absolute": seconds("AGRION_INTERVIEW_ABSOLUTE_SECONDS", 300),
        })

    @app.errorhandler(404)
    def not_found(error):
        return jsonify(error="not_found"), 404

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Unhandled server error")
        return jsonify(error="internal_server_error"), 500

    return app
