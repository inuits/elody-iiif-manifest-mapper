import logging
import os
import requests
import secrets

from flask import Flask
from flask_restful import Api
from healthcheck import HealthCheck

if os.getenv("SENTRY_ENABLED", False) in ["True", "true", True]:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        environment=os.getenv("NOMAD_NAMESPACE"),
    )

app = Flask(__name__)
api = Api(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def iiif_available():
    return True, requests.get(f'{os.getenv("IMAGE_API_URL")}/health').text


health = HealthCheck()
if os.getenv("HEALTH_CHECK_EXTERNAL_SERVICES", True) in ["True", "true", True]:
    health.add_check(iiif_available)

app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

from resources.manifest import Manifest

api.add_resource(
    Manifest,
    "/manifest/<string:entity_id>",
    "/manifest/<string:entity_id>/<int:version>",
)

if __name__ == "__main__":
    app.run()
