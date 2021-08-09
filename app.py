import json
import os

import requests
from flask import Flask
from flask_restful import Api

app = Flask(__name__)

app.config.update(
    {
        "SECRET_KEY": "something",
        "TESTING": os.getenv("TESTING"),
        "DEBUG": os.getenv("DEBUG"),
    }
)
api = Api(app)

from resources.GetManifest import GetManifest

api.add_resource(GetManifest, "/manifest/<string:entity_id>")
