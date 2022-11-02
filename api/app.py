import logging
import os
import requests
import sentry_sdk

from flask import Flask
from flask_restful import Api
from healthcheck import HealthCheck
from inuits_jwt_auth.authorization import JWTValidator, MyResourceProtector
from sentry_sdk.integrations.flask import FlaskIntegration

if os.getenv("SENTRY_ENABLED", False):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        environment=os.getenv("NOMAD_NAMESPACE"),
    )

app = Flask(__name__)
api = Api(app)
app.config.update(
    {
        "SECRET_KEY": "SomethingNotEntirelySecret",
        "TESTING": True,
        "DEBUG": True,
    }
)

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

require_oauth = MyResourceProtector(
    logger,
    os.getenv("REQUIRE_TOKEN", True) in ["True", "true", True],
)
validator = JWTValidator(
    logger,
    os.getenv("STATIC_ISSUER", False),
    os.getenv("STATIC_PUBLIC_KEY", False),
    os.getenv("REALMS", "").split(","),
    os.getenv("ROLE_PERMISSION_FILE", "role_permission.json"),
    os.getenv("SUPER_ADMIN_ROLE", "role_super_admin"),
    os.getenv("REMOTE_TOKEN_VALIDATION", False),
    os.getenv("REMOTE_PUBLIC_KEY", False),
)
require_oauth.register_token_validator(validator)


def iiif_available():
    return True, requests.get(f'{os.getenv("IMAGE_API_URL")}/health').text


health = HealthCheck()
if os.getenv("HEALTH_CHECK_EXTERNAL_SERVICES", True) in ["True", "true", True]:
    health.add_check(iiif_available)

app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

from resources.manifest import Manifest

api.add_resource(Manifest, "/manifest/<string:entity_id>")


@app.after_request
def add_header(response):
    response.headers["Jaeger-trace-id"] = os.getenv("JAEGER_TRACE_ID", "default-id")
    return response


if __name__ == "__main__":
    app.run(debug=True)
