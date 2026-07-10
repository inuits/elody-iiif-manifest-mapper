<p align="center">
  <a href="https://elody.eu"><img src="https://elody.eu/images/logo.svg" alt="Elody" width="96" /></a>
</p>

<p align="center">Part of <a href="https://elody.eu">Elody</a> — the open semantic data platform.</p>

# Inuits DAMS IIIF Manifest Mapper

Flask service that turns Elody entities into [IIIF Presentation API](https://iiif.io/api/presentation/) manifests and collections. Backed by `iiif-prezi3`; consumes entity data from collection-api.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/manifest/<entity_id>` | Generate a IIIF manifest for the entity (latest presentation-API version). |
| `GET` | `/manifest/<entity_id>/<version>` | Same, pinned to a specific presentation-API version. |
| `GET` | `/collection/<root_entity_id>` | Generate a IIIF collection rooted at the given entity. |
| `GET` | `/collection/<root_entity_id>/<config_entity_id>` | Collection generated using a specific config entity. |
| `GET` | `/iiif/manifest/<entity_id>` | Manifest generation using the configurable generator (per-client rules in `config/*.json`). |
| `POST` | `/pre-generate` | Trigger background pre-generation of manifests for a set of entities. |
| `GET` | `/health` | Liveness probe. |

## Layout

- `api/app.py` — Flask + Flask-RESTful bootstrap.
- `api/manifest_generator.py`, `collection_generator.py`, `generator.py`, `generatorv3.py` — presentation-API generators (v2 and v3).
- `api/base_generator.py` — shared base class.
- `api/collection_config.py` — per-client configuration loader for the configurable generator.
- `api/resources/` — Flask-RESTful resource classes matching the routes above.
- `config/*.json` — client-specific mapping rules (e.g. `wetenschatten.json`).
- `docker/` — container build.
- `examples/` — sample outputs for reference.
- `validate_endpoints.py` — helper for validating generated manifests against IIIF spec.

## Local setup

Elody's common repository contains the shared development environment. See [elody-common](https://gitlab.inuits.io/rnd/inuits/elody/elody-common) for how to run this service alongside collection-api, storage-api, cantaloupe, and the PWA.

## Dependencies

Python 3, Flask, `iiif-prezi3`, `elody` client library, `Pillow`, `PyLD`. Full pin list in `requirements.txt`.
