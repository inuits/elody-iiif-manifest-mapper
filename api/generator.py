import requests

from exceptions import EntityDoesNotExist, NoMediafiles
from iiif_prezi.factory import ManifestFactory


class ManifestGenerator:
    def __init__(
        self, collection_api_url, image_api_url, presentation_api_url, static_jwt=None
    ):
        self.collection_api_base_url = collection_api_url
        self.iiif_base_url = image_api_url
        self.prezi_base_url = presentation_api_url
        self.headers = {"Authorization": f"Bearer {static_jwt}"}
        self.default_copyright = (
            "https://rightsstatements.org/page/InC/1.0/?language=en"
        )
        self.license_mapping = {
            "CC BY-NC 4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
            "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
            "CC BY-NC-ND 4.0": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "Copyright Undetermined": "https://rightsstatements.org/page/UND/1.0/",
            "In Copyright - non-commercial use permitted": "http://rightsstatements.org/vocab/InC-NC/1.0/",
            "In Copyright - unknown rightsholder": "http://rightsstatements.org/vocab/InC-RUU/1.0/",
            "In Copyright": "http://rightsstatements.org/vocab/InC/1.0/",
            "Public Domain Mark 1.0": "https://creativecommons.org/publicdomain/mark/1.0/",
        }

    def __get_manifest_factory(self):
        fac = ManifestFactory()
        fac.set_iiif_image_info(2.0, 2)
        fac.set_base_prezi_uri(self.prezi_base_url)
        fac.set_base_image_uri(f"{self.iiif_base_url}/iiif/2/")
        return fac

    def __get_license_for_mediafile(self, license_name):
        return self.license_mapping.get(license_name, self.default_copyright)

    def __get_item_metadata_value(self, item, key, include_lang=False):
        for entry in item["metadata"]:
            if entry["key"] == key:
                if include_lang:
                    return entry["lang"], entry["value"]
                return entry["value"]
        return False

    def __check_entity(self, entity):
        if "message" in entity and "metadata" not in entity:
            raise EntityDoesNotExist(entity["message"])

    def __check_mediafiles(self, mediafiles):
        if not mediafiles or len(mediafiles) == 0:
            raise NoMediafiles("You don't have permission to access this resource")

    def __get_mediafile_filename(self, mediafile):
        if "transcode_filename" in mediafile:
            return mediafile["transcode_filename"]
        return mediafile["filename"]

    def generate_manifest(self, entity_id):
        entity = requests.get(
            f"{self.collection_api_base_url}/entities/{entity_id}",
            headers=self.headers,
        ).json()
        self.__check_entity(entity)
        mediafiles = requests.get(
            f"{self.collection_api_base_url}/entities/{entity_id}/mediafiles",
            headers=self.headers,
        ).json()
        self.__check_mediafiles(mediafiles)
        lang, title = self.__get_item_metadata_value(entity, "title", True)
        fac = self.__get_manifest_factory()
        manifest = fac.manifest(
            ident=f"{self.prezi_base_url}/manifest/{entity_id}", label={lang: title}
        )
        description = self.__get_item_metadata_value(entity, "description")
        manifest.set_description(description)
        manifest.rendering = {"@id": entity["data"]["@id"]}
        seq = manifest.sequence()
        for mediafile in mediafiles:
            ident = self.__get_mediafile_filename(mediafile)
            cvs = seq.canvas(ident=ident, label=ident)
            image = cvs.set_image_annotation(ident, iiif=True)
            image.license = self.__get_license_for_mediafile(
                self.__get_item_metadata_value(mediafile, "rights")
            )
        return manifest.toJSON(top=True)
