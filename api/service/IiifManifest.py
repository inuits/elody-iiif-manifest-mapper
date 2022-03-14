import json
import os
import requests

from iiif_prezi.factory import ManifestFactory
from job_helper.job_helper import JobHelper

job_helper = JobHelper(
    job_api_base_url=os.getenv("JOB_API_BASE_URL", "http://localhost:8000"),
    static_jwt=os.getenv("STATIC_JWT", False),
)

license_mapping = {
    "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "In Copyright": "https://rightsstatements.org/page/InC/1.0/?language=en",
}
default_copyright_value = "https://rightsstatements.org/page/InC/1.0/?language=en"


def get_value_from_key_in_dict(key, dict, include_lang=False):
    for keyvalues in dict:
        if keyvalues["key"] == key:
            if include_lang:
                return keyvalues["lang"], keyvalues["value"]
            return keyvalues["value"]
    return False


class IiifManifest:
    def __init__(
        self, collection_api_base_url, iiif_base_url, prezi_base_url, api_jwt_token=None
    ):
        self.collection_api_base_url = collection_api_base_url
        self.iiif_base_url = iiif_base_url
        self.prezi_base_url = prezi_base_url
        self.headers = {"Authorization": "Bearer {}".format(api_jwt_token)}

    def generate_manifest(self, entity_id):
        parent_job = job_helper.create_new_job(
            job_type="generate_manifest", job_info="Generate manifest parent job"
        )
        try:
            entity = requests.get(
                f"{self.collection_api_base_url}/entities/{entity_id}",
                headers=self.headers,
            ).json()
            mediafiles = requests.get(
                f"{self.collection_api_base_url}/entities/{entity_id}/mediafiles",
                headers=self.headers,
            ).json()
            parent_job = job_helper.progress_job(
                parent_job, amount_of_jobs=len(mediafiles)
            )
            entity_metadata = entity["metadata"]
            lang, title = get_value_from_key_in_dict("title", entity_metadata, True)
            fac = self.__get_manifest_factory()
            manifest = fac.manifest(label={lang: title})
            description = get_value_from_key_in_dict("description", entity_metadata)
            manifest.set_description(description)
            manifest.rendering = {"@id": entity["data"]["@id"]}
            seq = manifest.sequence()
            for mediafile in mediafiles:
                job = job_helper.create_new_job(
                    job_type="generate_manifest", job_info="Generate manifest"
                )
                parent_job_id = (
                    parent_job["_key"] if "_key" in parent_job else parent_job["_id"]
                )
                job = job_helper.progress_job(job, parent_job_id=parent_job_id)
                try:
                    id = mediafile["original_file_location"].rsplit("/", 1)[1]
                    job = job_helper.progress_job(job, mediafile_id=id)
                except Exception as ex:
                    job_helper.fail_job(job, "Missing mediafile id")
                    job_helper.fail_job(parent_job, str(ex))
                try:
                    cvs = seq.canvas(ident=id, label=mediafile["filename"])
                    image = cvs.set_image_annotation(id, iiif=True)
                    image.license = self.__get_license_for_mediafile(
                        get_value_from_key_in_dict("rights", mediafile["metadata"])
                    )
                    job_helper.finish_job(job)
                except Exception as ex:
                    seq.canvases.remove(cvs)
                    job_helper.fail_job(job, str(ex))
                    job_helper.fail_job(parent_job, str(ex))
            job_helper.finish_job(parent_job)
            return manifest.toJSON()
        except Exception as ex:
            job_helper.fail_job(parent_job, str(ex))

    def __get_manifest_factory(self):
        fac = ManifestFactory()
        fac.set_iiif_image_info(2.0, 2)
        fac.set_base_prezi_uri(self.prezi_base_url)
        fac.set_base_image_uri(self.iiif_base_url + "/iiif/2/")
        return fac

    def __get_license_for_mediafile(self, license_name):
        if license_name in license_mapping:
            return license_mapping[license_name]
        else:
            return default_copyright_value
