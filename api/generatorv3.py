import json
import logging

from base_generator import BaseGenerator
from iiif_prezi3 import Manifest, KeyValueString

logger = logging.getLogger(__name__)


class ManifestGeneratorv3(BaseGenerator):
    def __add_canvas_to_manifest(self, manifest, mediafile):
        # Get filename from various possible locations
        filename = self._get_mediafile_filename(mediafile)
        if not filename:
            return False

        source = self._get_item_metadata_value(mediafile, "source")
        image_url = self.image_api_url_ext + "/iiif/3/" + filename

        # Get mimetype
        mimetype = mediafile.get("mimetype")
        if not mimetype:
            metadata = mediafile.get("metadata", {})
            if isinstance(metadata, dict):
                mimetype = metadata.get("mimetype", "image/jpeg")
            else:
                mimetype = "image/jpeg"

        canvas = manifest.make_canvas(
            id=self.presentation_api_url + "canvas/" + filename + ".json",
            label=filename,
            rights=self._get_license_for_mediafile(mediafile),
            requiredStatement=KeyValueString(label="Attribution", value=source),
            height=mediafile["img_height"],
            width=mediafile["img_width"],
        )
        canvas.add_image(
            image_url=image_url,
            height=mediafile["img_height"],
            width=mediafile["img_width"],
            anno_page_id="https://annotationpageLink?",
            anno_id="https://annotationLink",
            thumbnail={
                "id": f"{image_url}/full/max/0/default.jpg",
                "type": mimetype,
            },
        )
        return True

    def _get_mediafile_filename(self, mediafile):
        """Extract filename from mediafile in various formats."""
        # Direct fields
        if mediafile.get("transcode_filename"):
            return mediafile["transcode_filename"]
        if mediafile.get("filename"):
            return mediafile["filename"]
        if mediafile.get("display_filename"):
            return mediafile["display_filename"]

        # From metadata dict
        metadata = mediafile.get("metadata", {})
        if isinstance(metadata, dict):
            if metadata.get("filename"):
                return metadata["filename"]

        # From metadata array (Elody format)
        if isinstance(metadata, list):
            for m in metadata:
                if m.get("key") == "filename":
                    return m.get("value")

        # From identifiers
        for identifier in mediafile.get("identifiers", []):
            if "." in identifier and not identifier.startswith("MED-"):
                return identifier

        return None

    def __check_valid_identifier(self, mediafile):
        filename = self._get_mediafile_filename(mediafile)
        if not filename:
            return False
        if not re.match(r"^[^-]{32}-.*$", filename):
            return False
        return True

    def _get_mediafiles_for_entity(self, entity):
        """
        Get mediafiles for an entity using multiple strategies.

        1. Try /entities/{id}/mediafiles endpoint
        2. Fall back to fetching via relations (hasMediafile)
        3. Fall back to fetching via primary_mediafile_id
        """
        entity_id = entity.get("_id") or entity.get("id")
        mediafiles = []

        # Strategy 1: Try the mediafiles endpoint
        try:
            response = self._get_from_collection_api(
                f"/entities/{entity_id}/mediafiles"
            )
            if response and response.get("results"):
                return response
        except Exception as e:
            logger.debug(f"Mediafiles endpoint failed for {entity_id}: {e}")

        # Strategy 2: Get from relations
        for relation in entity.get("relations", []):
            if relation.get("type") in ("hasMediafile", "hasPrimaryMediafile"):
                mediafile_id = relation.get("key")
                if mediafile_id:
                    try:
                        mediafile = self._get_from_collection_api(
                            f"/mediafiles/{mediafile_id}", entity=True
                        )
                        if mediafile:
                            mediafiles.append(mediafile)
                    except Exception as e:
                        logger.warning(f"Failed to fetch mediafile {mediafile_id}: {e}")

        # Strategy 3: Use primary_mediafile_id
        if not mediafiles and entity.get("primary_mediafile_id"):
            try:
                mediafile = self._get_from_collection_api(
                    f"/mediafiles/{entity['primary_mediafile_id']}", entity=True
                )
                if mediafile:
                    mediafiles.append(mediafile)
            except Exception as e:
                logger.warning(f"Failed to fetch primary mediafile: {e}")

        return {"results": mediafiles} if mediafiles else {"results": []}

    def generate_manifest(self, entity_id):
        entity = self._get_from_collection_api(f"/entities/{entity_id}", entity=True)
        mediafiles = self._get_mediafiles_for_entity(entity)

        title = self._get_item_metadata_value(entity, "title", False)
        description = self._get_item_metadata_value(entity, "description")
        manifest = Manifest(
            id=f"{self.presentation_api_url}/manifest/{entity_id}",
            label={"nl": [title]},
            summary={"nl": [description]},
            rendering={
                "id": entity["data"]["@id"],
                "type": entity["data"]["@type"],
                "label": {"nl": [title]},
            },
        )
        for mediafile in mediafiles:
            self.__add_canvas_to_manifest(manifest, mediafile)
        return json.loads(manifest.json())
