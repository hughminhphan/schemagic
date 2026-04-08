import sys
import os
from contextlib import asynccontextmanager

os.environ["SCHEMAGIC_STANDALONE"] = "1"

# Add repo root to sys.path so engine/ and server/ are importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.job_store import JobStore
from server.routes import pipeline, files, library


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.jobs = JobStore()
    yield
    app.state.jobs.shutdown()


app = FastAPI(title="scheMAGIC API", lifespan=lifespan)

_default_origins = [
    "http://localhost:3000",
    "https://schemagic.design",
    "https://www.schemagic.design",
]
_origins = os.environ.get("ALLOWED_ORIGINS", "").split(",") if os.environ.get("ALLOWED_ORIGINS") else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(library.router, prefix="/api")
