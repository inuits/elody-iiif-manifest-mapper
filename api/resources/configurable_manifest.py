"""
Configurable IIIF Manifest REST endpoint.

Provides REST API for generating IIIF v3 Manifests with JSON config support,
following the same pattern as the collection endpoint.
"""

import logging

from flask import request
from flask_restful import Resource

from manifest_generator import ConfigurableManifestGenerator
from elody.exceptions import NotFoundException

logger = logging.getLogger(__name__)


class ConfigurableManifest(Resource):
    """
    REST resource for configurable IIIF Manifest generation.

    Endpoints:
        GET /iiif/manifest/<entity_id>
            Generate manifest using default or file-based configuration

        POST /iiif/manifest/<entity_id>
            Generate manifest using config from request body

    Query Parameters:
        config_file: Name of JSON config file (without .json extension).
                    Loads config from config/{config_file}.json.
    """

    def __init__(self):
        self.generator = ConfigurableManifestGenerator()

    def get(self, entity_id: str):
        """
        Generate an IIIF v3 Manifest.

        Args:
            entity_id: ID of the entity to generate manifest for

        Query Parameters:
            config_file: Name of JSON config file (without .json extension)

        Returns:
            IIIF v3 Manifest JSON

        Raises:
            404: If entity not found
        """
        config_file = request.args.get("config_file", type=str)
        return self._generate(entity_id=entity_id, config_file=config_file, config_dict=None)

    def post(self, entity_id: str):
        """
        Generate an IIIF v3 Manifest using config from request body.

        Args:
            entity_id: ID of the entity to generate manifest for

        Request Body:
            JSON config object with metadataMappings, rightsUri, attribution, etc.

        Returns:
            IIIF v3 Manifest JSON

        Raises:
            400: If request body is not valid JSON
            404: If entity not found
        """
        config_dict = request.get_json()
        if not config_dict:
            return {
                "error": "Bad request",
                "message": "Request body must contain a valid JSON config",
            }, 400

        return self._generate(entity_id=entity_id, config_file=None, config_dict=config_dict)

    def _generate(self, entity_id: str, config_file: str = None, config_dict: dict = None):
        """Internal method to generate manifest."""
        # Copy authorization header from request
        auth_header = request.headers.get("Authorization")
        if auth_header:
            self.generator.headers["Authorization"] = auth_header

        try:
            manifest = self.generator.generate_manifest(
                entity_id=entity_id,
                config_file=config_file,
                config_dict=config_dict,
            )

            return manifest, 200, {
                "Content-Type": "application/ld+json",
                "Access-Control-Allow-Origin": "*",
            }

        except NotFoundException:
            return {
                "error": "Entity not found",
                "message": f"Entity with ID '{entity_id}' was not found",
            }, 404

        except Exception as e:
            logger.exception(f"Error generating manifest: {e}")
            return {
                "error": "Internal server error",
                "message": str(e),
            }, 500
