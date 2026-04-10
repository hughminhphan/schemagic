import os

from fastapi import APIRouter
from pydantic import BaseModel

from engine.core.project_detector import detect_kicad_project

router = APIRouter()


class KicadProjectResponse(BaseModel):
    project_dir: str | None = None
    project_name: str | None = None


@router.get("/kicad-project", response_model=KicadProjectResponse)
async def get_kicad_project():
    project_dir = detect_kicad_project()
    project_name = None
    if project_dir:
        # Derive name from the directory (matches .kicad_pro basename)
        project_name = os.path.basename(project_dir)
    return KicadProjectResponse(project_dir=project_dir, project_name=project_name)
