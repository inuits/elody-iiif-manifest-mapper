import app
import os

from flask_restful import Resource, abort
from flask import after_this_request
from service.IiifManifest import IiifManifest


class GetManifest(Resource):
    def __init__(self):
        self.iiif_manifest = IiifManifest(
            os.getenv("COLLECTION_API_BASE_URL"),
            os.getenv("IIIF_BASE_URL"),
            os.getenv("PREZI_BASE_URL"),
            os.getenv("STATIC_JWT", "None"),
        )

    @app.require_oauth()
    def get(self, entity_id):
        @after_this_request
        def add_header(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response

        manifest = self.iiif_manifest.generate_manifest(entity_id)
        if not manifest:
            return abort(
                500, message="Something went wrong while generating the manifest"
            )
        return manifest
