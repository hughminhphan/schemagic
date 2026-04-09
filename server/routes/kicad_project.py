from fastapi import APIRouter
from pydantic import BaseModel

from engine.core.project_detector import detect_kicad_project

router = APIRouter()


class KicadProjectResponse(BaseModel):
    project_dir: str | None = None


@router.get("/kicad-project", response_model=KicadProjectResponse)
async def get_kicad_project():
    project_dir = detect_kicad_project()
    return KicadProjectResponse(project_dir=project_dir)
