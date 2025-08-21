import os
from dotenv import load_dotenv
from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Architecture Generator API"
    PROJECT_VERSION: str = "2.0.0"
    CORS_ORIGINS: list = [
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
        "http://127.0.0.1:3000",
        "http://localhost:5174",
    ]
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY")
    AVAILABLE_ICONS: list = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

settings = Settings()