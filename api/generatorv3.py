import json
import re
from urllib.parse import quote

from base_generator import BaseGenerator
from elody.exceptions import NoMediafilesException
from iiif_prezi3 import KeyValueString, Manifest


class ManifestGeneratorv3(BaseGenerator):
    def __add_canvas_to_manifest(self, manifest, mediafile):
        id = quote(mediafile.get("transcode_filename", mediafile["filename"]))
        source = self._get_item_metadata_value(mediafile, "source")
        image_url = self.image_api_url_ext + "/iiif/3/" + id
        canvas = manifest.make_canvas(
            id=self.presentation_api_url + "canvas/" + id + ".json",
            label=self.__get_original_filename(mediafile),
            rights=self._get_license_for_mediafile(mediafile),
            requiredStatement=KeyValueString(
                label="Attribution", value=source if source else ""
            ),
        )
        canvas.add_image(
            image_url=image_url,
            anno_page_id="https://annotationpageLink?",
            anno_id="https://annotationLink",
            thumbnail={
                "id": f"{image_url}/full/max/0/default.jpg",
                "type": mediafile["mimetype"],
            },
        )
        return True

    def __get_original_filename(self, mediafile):
        original_filename = mediafile.get("original_filename")
        if original_filename:
            return original_filename
        filename = mediafile["filename"]
        match = re.match(r"^[^-]{32}-(.*)$", filename)
        return match.group(1) if match else filename

    def __check_valid_identifier(self, mediafile):
        ident = mediafile.get("transcode_filename", mediafile["filename"])
        return re.match(r"^[^-]{32}-.*$", ident)

    def generate_manifest(self, entity_id):
        entity = self._get_from_collection_api(
            f"/entities/{entity_id}",
            entity=True,
            check_canonical_uris=True,
            entity_id=entity_id,
        )

        mediafiles = self._get_from_collection_api(
            f"/entities/{entity_id}/mediafiles", mediafiles=True
        )
        title = self._get_item_metadata_value(entity, "title", False)
        description = self._get_item_metadata_value(entity, "description")
        manifest = Manifest(
            id=f"{self.presentation_api_url}/manifest/{entity_id}",
            label=title,
            summary=description,
            rendering={
                "id": entity.get("data", {}).get(
                    "@id", f"{self.collection_api_url}/entities/{entity_id}"
                ),
                "type": entity.get("data", {}).get(
                    "@type", entity.get("type", "asset")
                ),
                "label": title,
            },
        )

        any_mediafile_added = False
        for mediafile in mediafiles.get("results", []):
            if not self.__check_valid_identifier(mediafile):
                continue
            if self.__add_canvas_to_manifest(manifest, mediafile):
                any_mediafile_added = True

        if not any_mediafile_added:
            raise NoMediafilesException(
                f"Entity with id {entity_id} has no accessible mediafiles."
            )

        return json.loads(manifest.json())
