import app

from exceptions import EntityDoesNotExist, NoMediafiles, InvalidVersion
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
            app.logger.info("start")
            if version == 2:
                return ManifestGenerator().generate_manifest(entity_id)
            elif version == 3:
                return ManifestGeneratorv3().generate_manifest(entity_id)
            else:
                raise InvalidVersion('Only version 2 and 3 are supported.')
        except EntityDoesNotExist as ex:
            abort(404, message=str(ex))
        except InvalidVersion as ex:
            abort(400, message=str(ex))
        except NoMediafiles as ex:
            abort(403, message=str(ex))
        except Exception as ex:
            app.logger.error(f"Failed to generate manifest: {ex}")
            abort(500, message="Something went wrong while generating the manifest")
