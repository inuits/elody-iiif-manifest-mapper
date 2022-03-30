import logging
import os

import requests
from flask import Flask
from flask_restful import Api
from healthcheck import HealthCheck
from inuits_jwt_auth.authorization import MyResourceProtector, JWTValidator

app = Flask(__name__)

app.config.update(
    {"SECRET_KEY": "SomethingNotEntirelySecret", "TESTING": True, "DEBUG": True}
)

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def iiif_available():
    return True, requests.get(f'{os.getenv("IIIF_BASE_URL")}{"/health"}').text


health = HealthCheck()
if os.getenv("HEALTH_CHECK_EXTERNAL_SERVICES", True) in ["True", "true", True]:
    health.add_check(iiif_available)

app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

require_oauth = MyResourceProtector(
    os.getenv("REQUIRE_TOKEN", True) == ("True" or "true" or True),
)
validator = JWTValidator(
    logger,
    os.getenv("STATIC_ISSUER", False),
    os.getenv("STATIC_PUBLIC_KEY", False),
    os.getenv("REALMS", "").split(","),
    os.getenv("ROLE_PERMISSION_FILE", "role_permission.json"),
    os.getenv("SUPER_ADMIN_ROLE", "role_super_admin"),
    os.getenv("REMOTE_TOKEN_VALIDATION", False),
)
require_oauth.register_token_validator(validator)

api = Api(app)

from resources.manifest import Manifest

api.add_resource(Manifest, "/manifest/<string:entity_id>")
