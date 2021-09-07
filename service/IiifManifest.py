import os
import sys

from flask import g
from iiif_prezi.factory import ManifestFactory
import json
import requests
from job_helper.job_helper import JobHelper

job_helper = JobHelper(
    job_api_base_url=os.getenv("JOB_API_BASE_URL", "http://localhost:8000")

)


def get_value_from_key_in_dict(key, dict, include_lang=False):
    for keyvalues in dict:
        if keyvalues["key"] == key:
            if include_lang:
                return keyvalues["lang"], keyvalues["value"]
            return keyvalues["value"]
    return False


class IiifManifest:
    def __init__(self, collection_api_base_url, iiif_base_url, prezi_base_url):
        self.collection_api_base_url = collection_api_base_url
        self.iiif_base_url = iiif_base_url
        self.prezi_base_url = prezi_base_url

    def generate_manifest(self, entity_id):
        user = g.oidc_token_info["email"] if hasattr(g, "oidc_token_info") else "default_uploader"
        parent_job = job_helper.create_new_job(job_type="generate_manifest", job_info="Generate manifest parent job")
        parent_job = job_helper.progress_job(parent_job)
        fac = ManifestFactory()

        fac.set_iiif_image_info(2.0, 2)
        # Where the resources live on the web
        fac.set_base_prezi_uri(self.prezi_base_url)

        entity = json.loads(
            requests.get(self.collection_api_base_url + "/entities/" + entity_id).text
        )
        mediafiles = json.loads(
            requests.get(
                self.collection_api_base_url + "/entities/" + entity_id + "/mediafiles"
            ).text
        )

        fac.set_base_image_uri(self.iiif_base_url + "/iiif/2/")
        entity_metadata = entity["metadata"]
        lang, title = get_value_from_key_in_dict("title", entity_metadata, True)
        manifest = fac.manifest(label={lang: title})
        description = get_value_from_key_in_dict("description", entity_metadata)
        manifest.set_description(description)
        seq = manifest.sequence()
        for mediafile in mediafiles:
            job = job_helper.create_new_job(job_type="generate_manifest", job_info="Generate manifest")
            job = job_helper.progress_job(job, parent_job_id=parent_job["_id"])
            try:
                id = mediafile["original_file_location"].rsplit("/", 1)[1]
                job = job_helper.progress_job(job, mediafile_id=id)
            except:
                job_helper.fail_job(job, "Missing mediafile id")
            try:
                cvs = seq.canvas(ident=id, label=mediafile["filename"])
                cvs.set_image_annotation(id, iiif=True)
                job_helper.finish_job(job)
            except:
                job_helper.fail_job(job, sys.exc_info()[0])
        job_helper.finish_job(parent_job)
        return manifest.toJSON()
