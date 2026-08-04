"""
Configurable IIIF Manifest REST endpoint.

Provides REST API for generating IIIF v3 Manifests with JSON config support,
following the same pattern as the collection endpoint.
"""

import logging

import app
from elody.exceptions import (
    NoMediafilesException,
    NotFoundException,
)
from flask import redirect, request, url_for
from flask_restful import Resource, abort
from manifest_exceptions import RedirectException
from manifest_generator import ConfigurableManifestGenerator
from werkzeug.exceptions import Forbidden, Unauthorized

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

        Checks the pre-generation cache first for instant responses.
        """
        config_file = request.args.get("config_file", type=str)
        image_base_url = request.args.get("image_base_url", type=str)

        # Check pre-generation cache
        from resources.pre_generate import manifest_cache

        cache_key = (entity_id, config_file or "", image_base_url or "")
        cached = manifest_cache.get(cache_key)
        if cached is not None:
            return (
                cached,
                200,
                {
                    "Content-Type": "application/ld+json",
                    "Access-Control-Allow-Origin": "*",
                },
            )
        try:
            return self._generate(
                entity_id=entity_id,
                config_file=config_file,
                config_dict=None,
                image_base_url=image_base_url,
            )

        except NoMediafilesException:
            abort(
                403, message=f"Entity with id {entity_id} has no accessible mediafiles."
            )
        except NotFoundException:
            abort(404, message=f"Entity with id {entity_id} not found.")
        except RedirectException as r:
            return redirect(
                url_for("configurablemanifest", entity_id=r.canonical_id),
                code=301,
            )
        except Unauthorized:
            abort(
                401, message="This entity is not accessible to unauthenticated users."
            )
        except Forbidden:
            abort(403, message="This entity is not accessible to unauthorized users.")
        except Exception as ex:  # noqa: BLE001
            message = f"Failed to generate manifest: {ex}"
            app.logger.exception(message, exc_info=ex, stack_info=True)
            abort(500, message=message)

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

        return self._generate(
            entity_id=entity_id, config_file=None, config_dict=config_dict
        )

    def _generate(
        self,
        entity_id: str,
        config_file: str | None = None,
        config_dict: dict | None = None,
        image_base_url: str | None = None,
    ):
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
                image_base_url=image_base_url,
            )

            return (
                manifest,
                200,
                {
                    "Content-Type": "application/ld+json",
                    "Access-Control-Allow-Origin": "*",
                },
            )

        except RedirectException:
            raise

        except NotFoundException:
            return {
                "error": "Entity not found",
                "message": f"Entity with ID '{entity_id}' was not found",
            }, 404

        except Exception as e:
            logger.exception("Error generating manifest")
            return {
                "error": "Internal server error",
                "message": str(e),
            }, 500
