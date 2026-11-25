from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dagit.api.routes import router


app = FastAPI(title="DataGit API")

# Enable CORS for local web development & Vite dev server proxying
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)

# Mount frontend: prioritize Vite production bundle (frontend/dist),
# then fallback to frontend root or package static dir
repo_root = Path(__file__).resolve().parents[3]
frontend_dist = repo_root / "frontend" / "dist"
frontend_root = repo_root / "frontend"
package_static = Path(__file__).resolve().parent / "static"

if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
elif frontend_root.exists() and (frontend_root / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(frontend_root), html=True), name="frontend")
elif package_static.exists() and (package_static / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(package_static), html=True), name="frontend")
