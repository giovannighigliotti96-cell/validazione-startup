from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Firebase
    google_application_credentials: str = ""
    firebase_service_account_b64: str = ""
    firebase_project_id: str = ""

    # Security
    cron_token: str = "change-me"
    api_token: str = ""  # empty = manual endpoints are open
    pl_admin_password: str = ""  # Poltrona Libera admin panel (/pl/admin); empty = panel closed
    pl_test_emails: str = "giovannighigliotti96@gmail.com,example.com"  # excluded from the panel counts

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "validazione-startup/0.1"

    # Product Hunt
    producthunt_token: str = ""

    # Email
    email_provider: str = "none"  # smtp | resend | none
    notify_email_to: str = ""
    notify_email_from: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""

    # Scraper toggles / limits
    enable_indiehackers: bool = False
    enable_trustpilot: bool = False
    enable_trends: bool = True
    reddit_post_limit: int = 100
    reddit_comments_per_post: int = 20
    hn_hits_per_query: int = 200
    store_review_limit: int = 200
    lookback_days: int = 180
    request_delay_seconds: float = 1.5

    # LLM layer (any OpenAI-compatible provider: Mistral, Groq, OpenRouter...)
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "mistral-small-latest"
    llm_max_calls_per_run: int = 400
    llm_rpm: int = 50
    llm_batch_size: int = 25
    # Strong tier (few calls/month: enrichment, competitors, market, founder fit, discovery, interviews)
    llm_strong_base_url: str = ""
    llm_strong_api_key: str = ""
    llm_strong_model: str = ""
    llm_strong_rpm: int = 20
    tavily_api_key: str = ""
    youtube_api_key: str = ""
    brave_search_api_key: str = ""     # Brave Search API: $5 free monthly credit = 1,000 queries/month
    jina_api_key: str = ""             # Jina s.jina.ai search, free token quota
    llm_strong_fallback_models: str = "openai/gpt-oss-20b,qwen/qwen3.8-27b"  # each has its own daily token limit on Groq
    meta_pixel_id: str = ""
    landing_home_cluster: str = ""   # if set, "/" redirects to /lp/<cluster> (used by the product-named Cloud Run service)   # optional: injects the Meta pixel into hosted landing pages (PageView / Lead)

    public_base_url: str = "http://localhost:8000"

    # Salt for author hashing (any stable string; change = all hashes change)
    author_hash_salt: str = "validazione-startup"


@lru_cache
def get_settings() -> Settings:
    return Settings()
