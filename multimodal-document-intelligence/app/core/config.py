
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Multimodal Document Intelligence"
    environment: str = "development"
    debug: bool = True

    data_dir: Path = Path("data")
    originals_dir: Path = Path("data/originals")
    processed_dir: Path = Path("data/processed")
    page_images_dir: Path = Path("data/page_images")
    assets_dir: Path = Path("data/assets")
    logs_dir: Path = Path("data/logs")

    pdf_render_dpi: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
