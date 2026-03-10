from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Load environment variables early
load_dotenv()

from app.api.routes import router
from app.core.config import settings


app = FastAPI(title=settings.app_name)
app.include_router(router)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Serve the web UI at root
@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")
