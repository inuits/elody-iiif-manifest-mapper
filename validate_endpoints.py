#!/usr/bin/env python3
"""
IIIF Endpoint Validator

Validates that the IIIF manifest mapper service returns valid IIIF v3
Collection and Manifest JSON responses.

Usage:
    python validate_endpoints.py [--base-url URL] [--collection-api-url URL] [--config-file NAME]

Environment variables (used as defaults):
    PRESENTATION_API_URL: Base URL of the IIIF manifest mapper service
    COLLECTION_API_URL: Base URL of the Elody collection API
    STATIC_JWT: Bearer token for authenticated requests
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def make_request(url, token=None):
    """Make an HTTP GET request and return parsed JSON."""
    headers = {"Accept": "application/ld+json, application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": str(e), "body": body}, e.code
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}, 0


def validate_iiif_collection(data):
    """Validate basic IIIF v3 Collection structure. Returns list of errors."""
    errors = []

    if not isinstance(data, dict):
        return ["Response is not a JSON object"]

    ctx = data.get("@context")
    if ctx != "http://iiif.io/api/presentation/3/context.json":
        errors.append(f"@context missing or wrong: {ctx}")

    if data.get("type") != "Collection":
        errors.append(f"type is '{data.get('type')}', expected 'Collection'")

    if not data.get("id"):
        errors.append("id is missing")

    if not data.get("label"):
        errors.append("label is missing")

    items = data.get("items")
    if items is None:
        errors.append("items array is missing")
    elif not isinstance(items, list):
        errors.append(f"items is not an array: {type(items)}")
    else:
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{i}] is not an object")
                continue
            item_type = item.get("type")
            if item_type not in ("Collection", "Manifest"):
                errors.append(
                    f"items[{i}].type is '{item_type}', expected Collection or Manifest"
                )
            if not item.get("id"):
                errors.append(f"items[{i}].id is missing")

    return errors


def validate_iiif_manifest(data):
    """Validate basic IIIF v3 Manifest structure. Returns list of errors."""
    errors = []

    if not isinstance(data, dict):
        return ["Response is not a JSON object"]

    ctx = data.get("@context")
    if ctx != "http://iiif.io/api/presentation/3/context.json":
        errors.append(f"@context missing or wrong: {ctx}")

    if data.get("type") != "Manifest":
        errors.append(f"type is '{data.get('type')}', expected 'Manifest'")

    if not data.get("id"):
        errors.append("id is missing")

    if not data.get("label"):
        errors.append("label is missing")

    items = data.get("items")
    if items is None:
        errors.append("items array (canvases) is missing")
    elif not isinstance(items, list):
        errors.append(f"items is not an array: {type(items)}")
    else:
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{i}] is not an object")
                continue
            if item.get("type") != "Canvas":
                errors.append(
                    f"items[{i}].type is '{item.get('type')}', expected 'Canvas'"
                )

    return errors


def find_test_entity(collection_api_url, token=None):
    """Find a suitable test entity (context type with relations)."""
    for entity_type in ("context", "album", "media"):
        url = f"{collection_api_url.rstrip('/')}/entities?type={entity_type}&limit=5"
        data, status = make_request(url, token)
        if status != 200:
            continue

        results = data.get("results", data if isinstance(data, list) else [])
        for entity in results:
            entity_id = entity.get("_id") or entity.get("id")
            if entity_id:
                return entity_id, entity_type

    return None, None


def find_manifest_entity_from_collection(collection_data):
    """Extract a manifest entity ID from collection items for manifest validation."""
    items = collection_data.get("items", [])
    for item in items:
        if item.get("type") == "Manifest":
            manifest_id = item.get("id", "")
            # Extract entity ID from manifest URL (last path segment before query params)
            path = manifest_id.split("?")[0]
            parts = path.rstrip("/").split("/")
            if parts:
                return parts[-1]
        elif item.get("type") == "Collection":
            # Look for manifests in sub-collection items (if inlined)
            sub_items = item.get("items", [])
            for sub_item in sub_items:
                if sub_item.get("type") == "Manifest":
                    manifest_id = sub_item.get("id", "")
                    path = manifest_id.split("?")[0]
                    parts = path.rstrip("/").split("/")
                    if parts:
                        return parts[-1]
    return None


def main():
    parser = argparse.ArgumentParser(description="Validate IIIF endpoints")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PRESENTATION_API_URL", "http://localhost:5000"),
        help="Base URL of the IIIF manifest mapper service",
    )
    parser.add_argument(
        "--collection-api-url",
        default=os.getenv("COLLECTION_API_URL", "http://localhost:5001"),
        help="Base URL of the Elody collection API",
    )
    parser.add_argument(
        "--config-file",
        default="wetenschatten",
        help="Config file name to use (default: wetenschatten)",
    )
    parser.add_argument(
        "--entity-id",
        default=None,
        help="Specific root entity ID to test (auto-detects if not given)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("STATIC_JWT"),
        help="Bearer token for authenticated requests",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    passed = 0
    failed = 0

    def report(name, errors):
        nonlocal passed, failed
        if errors:
            failed += 1
            print(f"  FAIL  {name}")
            for e in errors:
                print(f"        - {e}")
        else:
            passed += 1
            print(f"  OK    {name}")

    # --- 1. Health check ---
    print("\n=== Step 1: Health Check ===")
    health_data, health_status = make_request(f"{base_url}/health", args.token)
    if health_status == 200:
        report("GET /health", [])
    else:
        report("GET /health", [f"Status {health_status}: {health_data}"])

    # --- 2. Find test entity ---
    print("\n=== Step 2: Find Test Entity ===")
    entity_id = args.entity_id
    if not entity_id:
        entity_id, entity_type = find_test_entity(args.collection_api_url, args.token)
        if entity_id:
            print(f"  Found test entity: {entity_id} (type: {entity_type})")
        else:
            print("  WARN  No test entities found in collection API.")
            print("        Use --entity-id to specify one manually.")
            # Still try endpoints with a dummy ID to test error handling
            entity_id = "test-entity-not-found"
    else:
        print(f"  Using provided entity: {entity_id}")

    # --- 3. Test Collection Endpoint ---
    print("\n=== Step 3: Collection Endpoint ===")
    collection_url = f"{base_url}/collection/{entity_id}?config_file={args.config_file}"
    print(f"  GET {collection_url}")
    collection_data, collection_status = make_request(collection_url, args.token)

    if collection_status == 200:
        errors = validate_iiif_collection(collection_data)
        report(f"GET /collection/{entity_id}", errors)
        print(f"        Items count: {len(collection_data.get('items', []))}")

        # Pretty print structure summary
        for item in collection_data.get("items", [])[:5]:
            label = item.get("label", {})
            label_text = ""
            for _lang, vals in label.items() if isinstance(label, dict) else []:
                label_text = vals[0] if vals else ""
                break
            print(f"        - [{item.get('type')}] {label_text or item.get('id', '?')}")
        if len(collection_data.get("items", [])) > 5:
            print(f"        ... and {len(collection_data['items']) - 5} more")
    elif collection_status == 404:
        report(
            f"GET /collection/{entity_id}",
            ["Entity not found (404). Try a different --entity-id."],
        )
    else:
        report(
            f"GET /collection/{entity_id}",
            [
                f"HTTP {collection_status}: {json.dumps(collection_data, indent=2)[:300]}"
            ],
        )

    # --- 4. Test Manifest Endpoint ---
    print("\n=== Step 4: Manifest Endpoint ===")

    # Try to get a manifest entity from the collection response
    manifest_entity_id = None
    if collection_status == 200:
        manifest_entity_id = find_manifest_entity_from_collection(collection_data)

    # Fall back to using the same entity ID
    if not manifest_entity_id:
        manifest_entity_id = entity_id

    manifest_url = (
        f"{base_url}/iiif/manifest/{manifest_entity_id}?config_file={args.config_file}"
    )
    print(f"  GET {manifest_url}")
    manifest_data, manifest_status = make_request(manifest_url, args.token)

    if manifest_status == 200:
        errors = validate_iiif_manifest(manifest_data)
        report(f"GET /iiif/manifest/{manifest_entity_id}", errors)
        canvas_count = len(manifest_data.get("items", []))
        print(f"        Canvases: {canvas_count}")
        if manifest_data.get("metadata"):
            print(f"        Metadata fields: {len(manifest_data['metadata'])}")
    elif manifest_status == 404:
        report(
            f"GET /iiif/manifest/{manifest_entity_id}",
            ["Entity not found (404). The entity may not have mediafiles."],
        )
    else:
        report(
            f"GET /iiif/manifest/{manifest_entity_id}",
            [f"HTTP {manifest_status}: {json.dumps(manifest_data, indent=2)[:300]}"],
        )

    # --- Summary ---
    print(f"\n=== Summary: {passed} passed, {failed} failed ===")

    if failed > 0:
        print("\nTips:")
        print("  - Ensure the IIIF manifest service is running")
        print("  - Check COLLECTION_API_URL and STATIC_JWT in .env")
        print("  - For REQUIRE_TOKEN=True, provide --token or set STATIC_JWT")
        print(f"  - Ensure entities exist for config '{args.config_file}'")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
