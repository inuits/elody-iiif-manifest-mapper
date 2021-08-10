import sys
import os

import app

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from service.IiifManifest import IiifManifest

from flask_restful import Resource


class GetManifest(Resource):
    def __init__(self):
        self.iiif_manifest = IiifManifest(
            os.getenv("COLLECTION_API_BASE_URL"),
            os.getenv("IIIF_BASE_URL"),
            os.getenv("PREZI_BASE_URL"),
        )

    @app.oidc.accept_token(
        require_token=os.getenv("REQUIRE_TOKEN", "True").lower() in ["true", "1"],
        scopes_required=["openid"],
    )
    def get(self, entity_id):
        return self.iiif_manifest.generate_manifest(entity_id)
