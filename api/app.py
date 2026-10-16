import logging
import os
import secrets

import requests
from flask import Flask
from flask_restful import Api
from healthcheck import HealthCheck
from werkzeug.middleware.proxy_fix import ProxyFix
from observability import init_observability

app = Flask(__name__)
init_observability(app)
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
if os.getenv("HEALTH_CHECK_EXTERNAL_SERVICES", "True") in ["True", "true", True]:
    health.add_check(iiif_available)

app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

from resources.collection import Collection  # noqa: E402
from resources.configurable_manifest import ConfigurableManifest  # noqa: E402
from resources.manifest import Manifest  # noqa: E402
from resources.pre_generate import PreGenerate  # noqa: E402

api.add_resource(
    Manifest,
    "/manifest/<string:entity_id>/2",
    "/<string:entity_id>/manifest/2",
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
    "/iiif/<string:entity_id>/manifest",
    "/manifest/<string:entity_id>",
    "/manifest/<string:entity_id>/3",
    "/<string:entity_id>/manifest",
    "/<string:entity_id>/manifest/3",
)

# Batch pre-generation endpoint
api.add_resource(
    PreGenerate,
    "/pre-generate",
)

if __name__ == "__main__":
    app.run()
