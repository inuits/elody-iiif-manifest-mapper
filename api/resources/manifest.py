import app
import os

from flask_restful import Resource, abort
from flask import after_this_request
from generator import ManifestGenerator


class Manifest(Resource):
    def __init__(self):
        self.manifest_generator = ManifestGenerator(
            os.getenv("COLLECTION_API_BASE_URL"),
            os.getenv("IIIF_BASE_URL"),
            os.getenv("PREZI_BASE_URL"),
            os.getenv("STATIC_JWT", "None"),
        )

    @app.require_oauth("get-manifest")
    def get(self, entity_id):
        @after_this_request
        def add_header(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response

        manifest = self.manifest_generator.generate_manifest(entity_id)
        if not manifest:
            abort(500, message="Something went wrong while generating the manifest")
        return manifest
