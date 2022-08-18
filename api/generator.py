import requests

from exceptions import EntityDoesNotExist, NoMediafiles
from iiif_prezi.factory import ManifestFactory


class ManifestGenerator:
    def __init__(
        self, collection_api_url, image_api_url, presentation_api_url, static_jwt
    ):
        self.collection_api_url = collection_api_url
        self.image_api_url = image_api_url
        self.presentation_api_url = presentation_api_url
        self.headers = {"Authorization": f"Bearer {static_jwt}"}

    def __add_canvas_to_sequence(self, seq, mediafile):
        ident = self.__get_mediafile_filename(mediafile)
        cvs = seq.canvas(ident=ident, label=ident)
        image = cvs.set_image_annotation(ident, iiif=True)
        image.license = self.__get_license_for_mediafile(mediafile)
        image.attribution = self.__get_attribution_for_mediafile(mediafile)
        image.resource.id = image.resource.id.replace("http://", "https://")
        image.resource.service.id = image.resource.service.id.replace(
            "http://", "https://"
        )

    def __check_entity(self, entity):
        if "message" in entity and "metadata" not in entity:
            raise EntityDoesNotExist(entity["message"])

    def __check_mediafiles(self, mediafiles):
        if not mediafiles or len(mediafiles) == 0:
            raise NoMediafiles("You don't have permission to access this resource")

    def __get_attribution_for_mediafile(self, mediafile):
        ret = f'source: {self.__get_item_metadata_value(mediafile, "source")}'
        if photographer := self.__get_item_metadata_value(mediafile, "photographer"):
            ret = f"photographer: {photographer}, {ret}"
        if rights_holder := self.__get_item_metadata_value(mediafile, "copyright"):
            ret = f"rightsholder: {rights_holder}, {ret}"
        return ret

    def __get_from_collection_api(self, endpoint):
        return requests.get(
            f"{self.collection_api_url}{endpoint}", headers=self.headers
        ).json()

    def __get_item_metadata_value(self, item, key, include_lang=False):
        for entry in [x for x in item["metadata"] if x["key"] == key]:
            return (entry["lang"], entry["value"]) if include_lang else entry["value"]
        return None

    def __get_license_for_mediafile(self, mediafile):
        license_name = self.__get_item_metadata_value(mediafile, "rights")
        return {
            "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
            "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
            "CC BY-NC-ND 4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "Copyright Undetermined": "https://rightsstatements.org/page/UND/1.0/",
            "In Copyright - non-commercial use permitted": "http://rightsstatements.org/vocab/InC-NC/1.0/",
            "In Copyright - unknown rightsholder": "http://rightsstatements.org/vocab/InC-RUU/1.0/",
            "In Copyright": "http://rightsstatements.org/vocab/InC/1.0/",
            "Public Domain Mark 1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
        }.get(license_name, "https://rightsstatements.org/page/InC/1.0/?language=en")

    def __get_manifest_factory(self):
        fac = ManifestFactory()
        fac.set_iiif_image_info(2.0, 2)
        fac.set_base_prezi_uri(self.presentation_api_url)
        fac.set_base_image_uri(f"{self.image_api_url}/iiif/2/")
        return fac

    def __get_mediafile_filename(self, mediafile):
        if "transcode_filename" in mediafile:
            return mediafile["transcode_filename"]
        return mediafile["filename"]

    def generate_manifest(self, entity_id):
        entity = self.__get_from_collection_api(f"/entities/{entity_id}")
        self.__check_entity(entity)
        mediafiles = self.__get_from_collection_api(f"/entities/{entity_id}/mediafiles")
        self.__check_mediafiles(mediafiles)
        lang, title = self.__get_item_metadata_value(entity, "title", True)
        fac = self.__get_manifest_factory()
        manifest = fac.manifest(
            ident=f"{self.presentation_api_url}/manifest/{entity_id}",
            label={lang: title},
        )
        manifest.set_description(self.__get_item_metadata_value(entity, "description"))
        manifest.rendering = {"@id": entity["data"]["@id"]}
        seq = manifest.sequence()
        for mediafile in mediafiles:
            self.__add_canvas_to_sequence(seq, mediafile)
        return manifest.toJSON(top=True)
