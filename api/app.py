import logging
import os

from flask import Flask
from flask_restful import Api
from inuits_jwt_auth.authorization import MyResourceProtector, JWTValidator

# OTel
from otel.tracer import Tracer
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace.export import BatchSpanProcessor

traceObject = Tracer("IIIF Manifest Mapper", __name__)
traceObject.configTracer()
traceObject.trace.get_tracer_provider().add_span_processor(
    # SimpleSpanProcessor(ConsoleSpanExporter())
    BatchSpanProcessor(traceObject.OTLPSpanExporter)
)


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

FlaskInstrumentor().instrument_app(app)

require_oauth = MyResourceProtector(
    os.getenv("STATIC_JWT", False),
    {},
    True if os.getenv("REQUIRE_TOKEN", True) == ("True" or "true" or True) else False,
)
validator = JWTValidator(
    logger,
    os.getenv("STATIC_JWT", False),
    os.getenv("STATIC_ISSUER", False),
    os.getenv("STATIC_PUBLIC_KEY", False),
    os.getenv("REALMS", "").split(","),
    True if os.getenv("REQUIRE_TOKEN", True) == ("True" or "true" or True) else False,
)
require_oauth.register_token_validator(validator)

api = Api(app)

from resources.GetManifest import GetManifest

api.add_resource(GetManifest, "/manifest/<string:entity_id>")
