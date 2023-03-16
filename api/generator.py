import os
import requests

from exceptions import EntityDoesNotExist, NoMediafiles
from iiif_prezi.factory import ManifestFactory


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ManifestGenerator(metaclass=Singleton):
    def __init__(self):
        self.collection_api_url = os.getenv("COLLECTION_API_URL")
        self.image_api_url = os.getenv("IMAGE_API_URL")
        self.image_api_url_ext = os.getenv("IMAGE_API_URL_EXT")
        self.presentation_api_url = os.getenv("PRESENTATION_API_URL")
        self.headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}

    def __add_canvas_to_sequence(self, seq, mediafile):
        ident = mediafile.get("transcode_filename", mediafile["filename"])
        cvs = seq.canvas(ident=ident, label=ident)
        image = cvs.set_image_annotation(ident, iiif=True)
        image.license = self.__get_license_for_mediafile(mediafile)
        image.attribution = self.__get_attribution_for_mediafile(mediafile)
        image.resource.id = image.resource.id.replace(
            self.image_api_url, self.image_api_url_ext
        )
        image.resource.service.id = image.resource.service.id.replace(
            self.image_api_url, self.image_api_url_ext
        )

    def __get_attribution_for_mediafile(self, mediafile):
        ret = f'source: {self.__get_item_metadata_value(mediafile, "source")}'
        if photographer := self.__get_item_metadata_value(mediafile, "photographer"):
            ret = f"photographer: {photographer}, {ret}"
        if rights_holder := self.__get_item_metadata_value(mediafile, "copyright"):
            ret = f"rightsholder: {rights_holder}, {ret}"
        return ret

    def __get_from_collection_api(self, endpoint, entity=False, mediafiles=False):
        req = requests.get(f"{self.collection_api_url}{endpoint}", headers=self.headers)
        if entity and req.status_code == 404:
            raise EntityDoesNotExist(req.json()["message"])
        elif mediafiles and not len(req.json()):
            raise NoMediafiles("You don't have permission to access this resource")
        return req.json()

    def __get_item_metadata_value(self, item, key, include_lang=False):
        for entry in [x for x in item["metadata"] if x["key"] == key]:
            return (entry["lang"], entry["value"]) if include_lang else entry["value"]
        return None

    def __get_license_for_mediafile(self, mediafile):
        license_name = self.__get_item_metadata_value(mediafile, "rights")
        return {
            "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
            "CC BY-NC-ND 4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
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
        fac.context_uri = fac.context_uri.replace("http://", "https:///")
        fac.default_image_api_profile = fac.default_image_api_profile.replace(
            "http://", "https:///"
        )
        fac.default_image_api_context = fac.default_image_api_context.replace(
            "http://", "https:///"
        )
        return fac

    def generate_manifest(self, entity_id):
        entity = self.__get_from_collection_api(f"/entities/{entity_id}", entity=True)
        mediafiles = self.__get_from_collection_api(
            f"/entities/{entity_id}/mediafiles", mediafiles=True
        )
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
