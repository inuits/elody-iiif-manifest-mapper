import json

from base_generator import BaseGenerator
from iiif_prezi3 import Manifest, KeyValueString


class ManifestGeneratorv3(BaseGenerator):
    def __add_canvas_to_manifest(self, manifest, mediafile):
        id = mediafile.get("transcode_identifier", mediafile["identifier"])
        source = self._get_item_metadata_value(mediafile, "source")
        image_url = self.image_api_url_ext + "/iiif/3/" + id
        canvas = manifest.make_canvas(
            id=self.presentation_api_url + "canvas/" + id + ".json",
            label=id,
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
                "type": mediafile["mimetype"],
            },
        )

    def generate_manifest(self, entity_id):
        entity = self._get_from_collection_api(f"/entities/{entity_id}", entity=True)
        mediafiles = self._get_from_collection_api(
            f"/entities/{entity_id}/mediafiles", mediafiles=True
        )
        lang, title = self._get_item_metadata_value(entity, "title", True)
        description = self._get_item_metadata_value(entity, "description")
        manifest = Manifest(
            id=f"{self.presentation_api_url}/manifest/{entity_id}",
            label={lang: [title]},
            summary={lang: [description]},
            rendering={
                "id": entity["data"]["@id"],
                "type": entity["data"]["@type"],
                "label": {lang: [title]},
            },
        )
        for mediafile in mediafiles:
            self.__add_canvas_to_manifest(manifest, mediafile)
        return json.loads(manifest.json())
