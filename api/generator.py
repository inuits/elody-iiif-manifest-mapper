import os
import requests

from exceptions import EntityDoesNotExist, NoMediafiles
from iiif_prezi.factory import ManifestFactory
from job_helper.job_helper import JobHelper

job_helper = JobHelper(
    job_api_base_url=os.getenv("JOB_API_BASE_URL"),
    static_jwt=os.getenv("STATIC_JWT", False),
)


class ManifestGenerator:
    def __init__(
        self, collection_api_url, image_api_url, presentation_api_url, static_jwt=None
    ):
        self.collection_api_base_url = collection_api_url
        self.iiif_base_url = image_api_url
        self.prezi_base_url = presentation_api_url
        self.headers = {"Authorization": f"Bearer {static_jwt}"}
        self.default_copyright_value = (
            "https://rightsstatements.org/page/InC/1.0/?language=en"
        )
        self.license_mapping = {
            "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "In Copyright": "https://rightsstatements.org/page/InC/1.0/?language=en",
        }

    def __get_manifest_factory(self):
        fac = ManifestFactory()
        fac.set_iiif_image_info(2.0, 2)
        fac.set_base_prezi_uri(self.prezi_base_url)
        fac.set_base_image_uri(self.iiif_base_url + "/iiif/2/")
        return fac

    def __get_license_for_mediafile(self, license_name):
        if license_name in self.license_mapping:
            return self.license_mapping[license_name]
        return self.default_copyright_value

    def __get_metadata_value_with_key(self, metadata, key, include_lang=False):
        for item in metadata:
            if item["key"] == key:
                if include_lang:
                    return item["lang"], item["value"]
                return item["value"]
        return False

    def __check_entity(self, entity):
        if "message" in entity and "metadata" not in entity:
            raise EntityDoesNotExist(entity["message"])

    def __check_mediafiles(self, mediafiles):
        if not mediafiles or len(mediafiles) == 0:
            raise NoMediafiles("You don't have permission to access this resource")

    def generate_manifest(self, entity_id):
        parent_job = job_helper.create_new_job(
            job_type="generate_manifest", job_info="Generate manifest parent job"
        )
        try:
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
            parent_job = job_helper.progress_job(
                parent_job, amount_of_jobs=len(mediafiles)
            )
            lang, title = self.__get_metadata_value_with_key(
                entity["metadata"], "title", True
            )
            fac = self.__get_manifest_factory()
            manifest = fac.manifest(ident=f"{self.prezi_base_url}/manifest/{entity_id}", label={lang: title})
            description = self.__get_metadata_value_with_key(
                entity["metadata"], "description"
            )
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
                        self.__get_metadata_value_with_key(
                            mediafile["metadata"], "rights"
                        )
                    )
                    job_helper.finish_job(job)
                except Exception as ex:
                    seq.canvases.remove(cvs)
                    job_helper.fail_job(job, str(ex))
                    job_helper.fail_job(parent_job, str(ex))
            job_helper.finish_job(parent_job)
            return manifest.toJSON(top=True)
        except Exception as ex:
            job_helper.fail_job(parent_job, str(ex))
            raise
