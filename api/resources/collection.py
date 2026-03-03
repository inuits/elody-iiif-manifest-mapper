"""
IIIF Collection REST endpoint.

Provides REST API for generating IIIF v3 Collections from Elody entities.
"""

import logging

from flask import request
from flask_restful import Resource

from collection_generator import CollectionGenerator
from elody.exceptions import NotFoundException

logger = logging.getLogger(__name__)


class Collection(Resource):
    """
    REST resource for IIIF Collection generation.

    Endpoints:
        GET /collection/<root_id>
            Generate collection using default configuration

        GET /collection/<root_id>/<config_id>
            Generate collection using specified configuration entity

        POST /collection/<root_id>
            Generate collection using config from request body

    Query Parameters:
        depth: Maximum depth to traverse (integer, optional)
        config_file: Name of JSON config file to use (without .json extension).
                    If provided, loads config from config/{config_file}.json.
                    Takes precedence over config_entity_id in URL path.
    """

    def __init__(self):
        self.generator = CollectionGenerator()

    def get(
        self,
        root_entity_id: str,
        config_entity_id: str = None,
    ):
        """
        Generate an IIIF v3 Collection.

        Args:
            root_entity_id: ID of the root entity to generate collection from
            config_entity_id: Optional ID of configuration entity

        Query Parameters:
            depth: Maximum depth to traverse
            config_file: Name of JSON config file (without .json extension)

        Returns:
            IIIF v3 Collection JSON

        Raises:
            404: If root entity or config entity not found
        """
        # Parse optional query parameters
        depth = request.args.get("depth", type=int)
        config_file = request.args.get("config_file", type=str)

        return self._generate(
            root_entity_id=root_entity_id,
            config_entity_id=config_entity_id,
            config_file=config_file,
            config_dict=None,
            depth=depth,
        )

    def post(
        self,
        root_entity_id: str,
    ):
        """
        Generate an IIIF v3 Collection using config from request body.

        Args:
            root_entity_id: ID of the root entity to generate collection from

        Request Body:
            JSON config object with traversalSteps, metadataMappings, etc.

        Query Parameters:
            depth: Maximum depth to traverse

        Returns:
            IIIF v3 Collection JSON

        Raises:
            400: If request body is not valid JSON
            404: If root entity not found
        """
        depth = request.args.get("depth", type=int)

        # Get config from request body
        config_dict = request.get_json()
        if not config_dict:
            return {
                "error": "Bad request",
                "message": "Request body must contain a valid JSON config",
            }, 400

        return self._generate(
            root_entity_id=root_entity_id,
            config_entity_id=None,
            config_file=None,
            config_dict=config_dict,
            depth=depth,
        )

    def _generate(
        self,
        root_entity_id: str,
        config_entity_id: str = None,
        config_file: str = None,
        config_dict: dict = None,
        depth: int = None,
    ):
        """Internal method to generate collection."""
        # Copy authorization header from request
        auth_header = request.headers.get("Authorization")
        if auth_header:
            self.generator.headers["Authorization"] = auth_header

        try:
            collection = self.generator.generate_collection(
                root_entity_id=root_entity_id,
                config_entity_id=config_entity_id,
                config_file=config_file,
                config_dict=config_dict,
                depth=depth,
            )

            return collection, 200, {
                "Content-Type": "application/ld+json",
                "Access-Control-Allow-Origin": "*",
            }

        except NotFoundException:
            return {
                "error": "Entity not found",
                "message": f"Entity with ID '{root_entity_id}' was not found",
            }, 404

        except Exception as e:
            logger.exception(f"Error generating collection: {e}")
            return {
                "error": "Internal server error",
                "message": str(e),
            }, 500
