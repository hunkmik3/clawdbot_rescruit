from typing import Any
import time

import httpx

from app.core.config import settings


class ApifyClient:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self) -> None:
        self.token = settings.apify_api_token
        self.timeout = httpx.Timeout(30.0)

    def _ensure_token(self) -> None:
        if not self.token:
            raise RuntimeError("APIFY_API_TOKEN is missing")

    def _actor_id_for_platform(self, platform: str) -> str:
        mapping = {
            "linkedin": settings.apify_actor_linkedin_id,
            "artstation": settings.apify_actor_artstation_id,
            "x": settings.apify_actor_x_id,
            "instagram": settings.apify_actor_instagram_id,
        }
        actor_id = mapping.get(platform.lower(), "")
        if not actor_id:
            raise RuntimeError(f"Missing actor id for platform: {platform}")
        return actor_id

    def start_run(self, platform: str, actor_input: dict[str, Any], actor_id_override: str | None = None) -> str:
        self._ensure_token()
        actor_id = actor_id_override or self._actor_id_for_platform(platform)
        # Apify API uses ~ as separator (e.g. "username~actor-name")
        # but human-readable URLs use / — auto-convert
        actor_id = actor_id.replace("/", "~")
        url = f"{self.BASE_URL}/acts/{actor_id}/runs"
        params = {"token": self.token}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, params=params, json=actor_input)
            response.raise_for_status()
            payload = response.json()

        run_id = payload.get("data", {}).get("id")
        if not run_id:
            raise RuntimeError(f"Failed to start Apify run for platform={platform}")
        return run_id

    def wait_for_run(self, run_id: str) -> dict[str, Any]:
        self._ensure_token()
        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        params = {"token": self.token}

        elapsed = 0
        interval = max(1, settings.apify_poll_interval_seconds)
        timeout = max(interval, settings.apify_poll_timeout_seconds)

        with httpx.Client(timeout=self.timeout) as client:
            while elapsed <= timeout:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json().get("data", {})
                status = payload.get("status")

                if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                    return payload

                elapsed += interval
                time.sleep(interval)

        raise TimeoutError(f"Apify run timed out: {run_id}")

    def get_dataset_items(self, dataset_id: str) -> list[dict[str, Any]]:
        self._ensure_token()
        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        params = {
            "token": self.token,
            "clean": "true",
            "format": "json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list):
            return data
        raise RuntimeError("Unexpected dataset format from Apify")

    def run_actor_and_fetch_items(
        self, platform: str, actor_input: dict[str, Any], actor_id_override: str | None = None
    ) -> list[dict[str, Any]]:
        run_id = self.start_run(platform=platform, actor_input=actor_input, actor_id_override=actor_id_override)
        run_data = self.wait_for_run(run_id)
        if run_data.get("status") != "SUCCEEDED":
            raise RuntimeError(f"Run failed for platform={platform}, run_id={run_id}, status={run_data.get('status')}")

        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            return []

        return self.get_dataset_items(dataset_id)
