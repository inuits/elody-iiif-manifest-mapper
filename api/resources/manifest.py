import app
import os

from exceptions import EntityDoesNotExist, NoMediafiles
from flask import after_this_request
from flask_restful import Resource, abort
from generator import ManifestGenerator


class Manifest(Resource):
    def __init__(self):
        self.manifest_generator = ManifestGenerator(
            os.getenv("COLLECTION_API_URL"),
            os.getenv("IMAGE_API_URL"),
            os.getenv("IMAGE_API_URL_EXT"),
            os.getenv("PRESENTATION_API_URL"),
            os.getenv("STATIC_JWT"),
        )

    @app.require_oauth("get-manifest")
    def get(self, entity_id):
        @after_this_request
        def add_header(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Content-Type"] = "application/ld+json"
            return response

        try:
            return self.manifest_generator.generate_manifest(entity_id)
        except EntityDoesNotExist as ex:
            abort(404, message=str(ex))
        except NoMediafiles as ex:
            abort(403, message=str(ex))
        except Exception as ex:
            app.logger.error(f"Failed to generate manifest: {ex}")
            abort(500, message="Something went wrong while generating the manifest")
