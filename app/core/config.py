from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Clawbot Apify MVP"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    apify_api_token: str = ""
    apify_actor_linkedin_id: str = "harvestapi/linkedin-profile-search"
    apify_actor_artstation_id: str = "contacts-api/artstation-email-scraper-fast-advanced-and-cheapest"
    apify_actor_x_id: str = "web.harvester/twitter-scraper"
    apify_actor_instagram_id: str = "shu8hvrXbJbY3Eb9W"

    apify_poll_interval_seconds: int = 5
    apify_poll_timeout_seconds: int = 300

    # RapidAPI (used for ArtStation)
    rapidapi_key: str = ""

    # Google Sheets Integration
    google_sheets_credentials_file: str = "service_account.json"
    google_sheet_id: str = ""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
