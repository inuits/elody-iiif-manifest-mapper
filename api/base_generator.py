import os
import requests

from elody.exceptions import NotFoundException, NoMediafilesException


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class BaseGenerator(metaclass=Singleton):
    def __init__(self):
        self.collection_api_url = os.getenv("COLLECTION_API_URL")
        self.image_api_url = os.getenv("IMAGE_API_URL")
        self.image_api_url_ext = os.getenv("IMAGE_API_URL_EXT")
        self.presentation_api_url = os.getenv("PRESENTATION_API_URL")
        self.headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}

    def _get_attribution_for_mediafile(self, mediafile):
        ret = f'source: {self._get_item_metadata_value(mediafile, "source")}'
        if photographer := self._get_item_metadata_value(mediafile, "photographer"):
            ret = f"photographer: {photographer}, {ret}"
        if rights_holder := self._get_item_metadata_value(mediafile, "copyright"):
            ret = f"rightsholder: {rights_holder}, {ret}"
        return ret

    def _get_from_collection_api(self, endpoint, entity=False, mediafiles=False):
        req = requests.get(f"{self.collection_api_url}{endpoint}", headers=self.headers)
        if entity and req.status_code == 404:
            raise NotFoundException(req.json()["message"])
        elif mediafiles and not len(req.json()):
            raise NoMediafilesException(
                "You don't have permission to access this resource"
            )
        return req.json()

    def _get_item_metadata_value(self, item, key, include_lang=False):
        for entry in [x for x in item["metadata"] if x["key"] == key]:
            return (entry["lang"], entry["value"]) if include_lang else entry["value"]
        return None

    def _get_license_for_mediafile(self, mediafile):
        license_name = self._get_item_metadata_value(mediafile, "rights")
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
