import re

from base_generator import BaseGenerator
from elody.exceptions import NoMediafilesException
from iiif_prezi.factory import ManifestFactory


class ManifestGenerator(BaseGenerator):
    def __add_canvas_to_sequence(self, seq, mediafile):
        ident = mediafile["_id"]
        # This is required for a part of the pre-authorize script in cantaloupe
        # to correctly identify the identifier. Not massively happy though,
        # feels like it should just be possible to properly url-encode it but
        # that leads to other errors
        ident = ident.replace(" ", "%20")
        cvs = seq.canvas(ident=ident, label=ident)
        image = cvs.set_image_annotation(ident, iiif=True)
        image.license = self._get_license_for_mediafile(mediafile)
        image.attribution = self._get_attribution_for_mediafile(mediafile)

        image.resource.id = image.resource.id.replace(
            self.image_api_url, self.image_api_url_ext
        )
        image.resource.service.id = image.resource.service.id.replace(
            self.image_api_url, self.image_api_url_ext
        )
        return True

    def __check_valid_identifier(self, mediafile):
        ident = mediafile.get("transcode_filename", mediafile["filename"])
        return re.match(r"^[^-]{32}-.*$", ident)

    def __get_manifest_factory(self):
        fac = ManifestFactory()
        fac.set_iiif_image_info(2.0, 2)
        fac.set_base_prezi_uri(self.presentation_api_url)
        fac.set_base_image_uri(f"{self.image_api_url}/iiif/2/")
        return fac

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
        fac = self.__get_manifest_factory()
        manifest = fac.manifest(
            ident=f"{self.presentation_api_url}/manifest/{entity_id}",
            label=title,
        )
        manifest.set_description(self._get_item_metadata_value(entity, "description"))
        manifest.rendering = {
            "@id": entity.get("data", {}).get(
                "@id", f"{self.collection_api_url}/entities/{entity_id}"
            )
        }
        seq = manifest.sequence()
        any_mediafile_added = False
        for mediafile in mediafiles.get("results", []):
            if not self.__check_valid_identifier(mediafile):
                continue
            if self.__add_canvas_to_sequence(seq, mediafile):
                any_mediafile_added = True

        if not any_mediafile_added:
            raise NoMediafilesException(
                f"Entity with id {entity_id} has no accessible mediafiles."
            )

        return manifest.toJSON(top=True)
