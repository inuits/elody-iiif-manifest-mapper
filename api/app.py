import logging
import os

from flask import Flask
from flask_restful import Api
from inuits_jwt_auth.authorization import MyResourceProtector, JWTValidator

app = Flask(__name__)

app.config.update(
    {
        "SECRET_KEY": "SomethingNotEntirelySecret",
        "TESTING": True,
        "DEBUG": True
    }
)

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

require_oauth = MyResourceProtector(os.getenv("STATIC_JWT", False))
validator = JWTValidator(logger, os.getenv("STATIC_JWT", False), os.getenv("STATIC_ISSUER", False),
                         os.getenv("STATIC_PUBLIC_KEY", False), os.getenv("REALMS", "").split(","))
require_oauth.register_token_validator(validator)

api = Api(app)

from resources.GetManifest import GetManifest

api.add_resource(GetManifest, "/manifest/<string:entity_id>")
