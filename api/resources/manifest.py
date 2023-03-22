from app import policy_factory, logger
from exceptions import EntityDoesNotExist, NoMediafiles
from flask import request, after_this_request
from flask_restful import Resource, abort
from generator import ManifestGenerator
from inuits_policy_based_auth import RequestContext


class Manifest(Resource):
    @policy_factory.apply_policies(RequestContext(request, ["get-manifest"]))
    def get(self, entity_id):
        @after_this_request
        def add_header(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            if response.status_code == 200:
                response.headers["Content-Type"] = "application/ld+json"
            return response

        try:
            return ManifestGenerator().generate_manifest(entity_id)
        except EntityDoesNotExist as ex:
            abort(404, message=str(ex))
        except NoMediafiles as ex:
            abort(403, message=str(ex))
        except Exception as ex:
            logger.error(f"Failed to generate manifest: {ex}")
            abort(500, message="Something went wrong while generating the manifest")
