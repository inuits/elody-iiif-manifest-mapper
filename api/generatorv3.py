import os
import requests
import app
import json


from exceptions import EntityDoesNotExist, NoMediafiles
from iiif_prezi3 import Manifest, KeyValueString

class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class ManifestGeneratorv3(metaclass=Singleton):
    def __init__(self):
        self.collection_api_url = os.getenv("COLLECTION_API_URL")
        self.image_api_url = os.getenv("IMAGE_API_URL")
        self.image_api_url_ext = os.getenv("IMAGE_API_URL_EXT")
        self.presentation_api_url = os.getenv("PRESENTATION_API_URL")
        self.headers = {"Authorization": f'Bearer {os.getenv("STATIC_JWT")}'}

    def __add_canvas_to_manifest(self, manifest, mediafile):
        id = mediafile.get("transcode_filename", mediafile["filename"])

        source = self.__get_item_metadata_value(mediafile, "source")
        image_url = self.image_api_url_ext + "/iiif/3/" + id
        canvas = manifest.make_canvas(
            id=self.presentation_api_url + "canvas/" + id + ".json",
            label=id,
            rights=self.__get_license_for_mediafile(mediafile),
            requiredStatement=KeyValueString(
                label="Attribution",
                value=source
            ),
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
                "id": f'{image_url}/full/{mediafile["img_width"]},{mediafile["img_height"]}/0/default.jpg',
                "type": mediafile["mimetype"]
            },
        )

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

    def generate_manifest(self, entity_id):
        entity = self.__get_from_collection_api(f"/entities/{entity_id}", entity=True)

        mediafiles = self.__get_from_collection_api(
            f"/entities/{entity_id}/mediafiles", mediafiles=True
        )

        lang, title = self.__get_item_metadata_value(entity, "title", True)
        description = self.__get_item_metadata_value(entity, "description")

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
