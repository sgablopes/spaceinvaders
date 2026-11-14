from flask import Blueprint, jsonify

health_blueprint = Blueprint("health", __name__, url_prefix="/api")


@health_blueprint.get("/health")
def health():
    return jsonify(application="Agrion", version="0.1.0", status="ok")
