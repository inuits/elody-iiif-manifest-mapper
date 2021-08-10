import json
import os

import requests
from flask import Flask
from flask_oidc import OpenIDConnect
from flask_restful import Api

app = Flask(__name__)

app.config.update(
    {
        "SECRET_KEY": "SomethingNotEntirelySecret",
        "TESTING": True,
        "DEBUG": True,
        "OIDC_CLIENT_SECRETS": "client_secrets.json",
        "OIDC_ID_TOKEN_COOKIE_SECURE": False,
        "OIDC_REQUIRE_VERIFIED_EMAIL": False,
        "OIDC_USER_INFO_ENABLED": True,
        "OIDC_OPENID_REALM": os.getenv("OIDC_OPENID_REALM"),
        "OIDC_SCOPES": ["openid", "email", "profile"],
        "OIDC_INTROSPECTION_AUTH_METHOD": "client_secret_post",
    }
)
oidc = OpenIDConnect(app)

api = Api(app)

from resources.GetManifest import GetManifest

api.add_resource(GetManifest, "/manifest/<string:entity_id>")
