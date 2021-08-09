import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from service.IiifManifest import IiifManifest

from flask_restful import Resource


class GetManifest(Resource):
    def __init__(self):
        self.iiif_manifest = IiifManifest(
            os.getenv("collection_api_base_url", "http://collection-api:8000"),
            os.getenv("iiif_base_url", "http://cantaloupe:8182"),
        )

    def get(self, entity_id):
        return self.iiif_manifest.generate_manifest(entity_id)
