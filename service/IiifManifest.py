from iiif_prezi.factory import ManifestFactory
import json
import requests


def get_value_from_key_in_dict(key, dict, include_lang=False):
    for keyvalues in dict:
        if keyvalues["key"] == key:
            if include_lang:
                return keyvalues["lang"], keyvalues["value"]
            return keyvalues["value"]
    return False


class IiifManifest:
    def __init__(self, collection_api_base_url, iiif_base_url):
        self.collection_api_base_url = collection_api_base_url
        self.iiif_base_url = iiif_base_url

    def generate_manifest(self, entity_id):
        fac = ManifestFactory()

        fac.set_iiif_image_info(2.0, 2)
        # Where the resources live on the web
        fac.set_base_prezi_uri("http://localhost")

        entity = json.loads(
            requests.get(self.collection_api_base_url + "/entities/" + entity_id).text
        )
        mediafiles = json.loads(
            requests.get(
                self.collection_api_base_url + "/entities/" + entity_id + "/mediafiles"
            ).text
        )

        fac.set_base_image_uri(self.iiif_base_url + "/iiif/3/")
        entity_metadata = entity["metadata"]
        lang, title = get_value_from_key_in_dict("title", entity_metadata, True)
        manifest = fac.manifest(label={lang: title})
        description = get_value_from_key_in_dict("description", entity_metadata)
        manifest.set_description(description)
        seq = manifest.sequence()
        for mediafile in mediafiles:
            id = mediafile["original_file_location"].rsplit("/", 1)[1]
            cvs = seq.canvas(ident=id, label=mediafile["filename"])
            cvs.set_image_annotation(id, iiif=True)

        return manifest.toJSON()
