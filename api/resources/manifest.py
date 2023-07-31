import app

from elody.exceptions import (
    NoMediafilesException,
    NotFoundException,
    UnsupportedVersionException,
)
from flask import after_this_request
from flask_restful import Resource, abort
from generator import ManifestGenerator
from generatorv3 import ManifestGeneratorv3


class Manifest(Resource):
    def get(self, entity_id, version=2):
        @after_this_request
        def add_header(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            if response.status_code == 200:
                response.headers["Content-Type"] = "application/ld+json"
            return response

        try:
            generator = {2: ManifestGenerator, 3: ManifestGeneratorv3}.get(version)
            if not generator:
                raise UnsupportedVersionException()
            generator().generate_manifest(entity_id)
        except NoMediafilesException:
            abort(
                403, message=f"Entity with id {entity_id} has no accessible mediafiles."
            )
        except NotFoundException:
            abort(404, message=f"Entity with id {entity_id} not found.")
        except UnsupportedVersionException:
            abort(
                400,
                message=f"Version {version} is not supported. Only version 2 & 3 are currently supported.",
            )
        except Exception as ex:
            message = f"Failed to generate manifest: {ex}"
            app.logger.error(message)
            abort(500, message=message)
