import os

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse

from server.job_store import JobStore

router = APIRouter()


def _get_jobs(request: Request) -> JobStore:
    return request.app.state.jobs


@router.get("/download/{job_id}/{filename:path}")
async def download_file(job_id: str, filename: str, request: Request):
    jobs = _get_jobs(request)
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    file_path = os.path.join(job["output_dir"], filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Prevent path traversal
    real_path = os.path.realpath(file_path)
    real_base = os.path.realpath(job["output_dir"])
    if not real_path.startswith(real_base):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream",
    )
