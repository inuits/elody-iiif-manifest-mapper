import logging
import os
import secrets

import requests
from flask import Flask
from flask_restful import Api
from healthcheck import HealthCheck
from werkzeug.middleware.proxy_fix import ProxyFix

if os.getenv("SENTRY_ENABLED", False) in ["True", "true", True]:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        environment=os.getenv("NOMAD_NAMESPACE"),
    )

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
api = Api(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def iiif_available():
    return True, requests.get(f"{os.getenv('IMAGE_API_URL')}/health").text


health = HealthCheck()
if os.getenv("HEALTH_CHECK_EXTERNAL_SERVICES", True) in ["True", "true", True]:
    health.add_check(iiif_available)

app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

from resources.collection import Collection
from resources.configurable_manifest import ConfigurableManifest
from resources.manifest import Manifest
from resources.pre_generate import PreGenerate

api.add_resource(
    Manifest,
    "/manifest/<string:entity_id>",
    "/manifest/<string:entity_id>/<int:version>",
    "/<string:entity_id>/manifest",
    "/<string:entity_id>/manifest/<int:version>",
)

api.add_resource(
    Collection,
    "/collection/<string:root_entity_id>",
    "/collection/<string:root_entity_id>/<string:config_entity_id>",
)

# New configurable manifest endpoint (same pattern as collection)
api.add_resource(
    ConfigurableManifest,
    "/iiif/manifest/<string:entity_id>",
)

# Batch pre-generation endpoint
api.add_resource(
    PreGenerate,
    "/pre-generate",
)

if __name__ == "__main__":
    app.run()
