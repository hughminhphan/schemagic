import asyncio
import json
import logging
import os
import threading
import dataclasses

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from server.schemas import (
    RunRequest, RunResponse,
    SelectPackageRequest, SelectPackageResponse,
    FinalizeRequest, FinalizeResponse,
    PinInfoSchema, PackageInfoSchema, MatchResultSchema,
    DatasheetSummarySchema, FileInfo, ModelInfo,
)
from server.job_store import JobStore

from engine.core.pipeline import Pipeline
from engine.core.models import PinInfo, PackageInfo

from server.license import validate_license_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_jobs(request: Request) -> JobStore:
    return request.app.state.jobs


async def require_license(x_license_token: str = Header(...)):
    """Validate the X-License-Token header on billable endpoints."""
    try:
        claims = validate_license_token(x_license_token)
        return claims
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid or expired license token")


def _datasheet_to_schema(ds) -> DatasheetSummarySchema:
    pkg = None
    if ds.package:
        pkg = PackageInfoSchema(
            name=ds.package.name,
            pin_count=ds.package.pin_count,
            ti_code=ds.package.ti_code or "",
            dimensions=ds.package.dimensions or "",
        )
    return DatasheetSummarySchema(
        part_number=ds.part_number,
        manufacturer=ds.manufacturer or "",
        description=ds.description or "",
        component_type=ds.component_type or "",
        package=pkg,
        datasheet_url=ds.datasheet_url or "",
        confidence=ds.confidence,
        pins=[
            PinInfoSchema(
                number=p.number,
                name=p.name,
                pin_type=p.pin_type,
                description=p.description or "",
                alt_numbers=p.alt_numbers or [],
                is_hidden=getattr(p, "is_hidden", False),
            )
            for p in ds.pins
        ],
    )


def _match_to_schema(m) -> MatchResultSchema:
    return MatchResultSchema(
        symbol_lib=m.symbol_lib or "",
        symbol_name=m.symbol_name or "",
        footprint_lib=m.footprint_lib or "",
        footprint_name=m.footprint_name or "",
        symbol_score=m.symbol_score,
        footprint_score=m.footprint_score,
        pin_mapping=m.pin_mapping or {},
    )


def _run_pipeline_thread(job_id: str, part_number: str, jobs: JobStore, local_pdf: str = None):
    job = jobs.get(job_id)
    if not job:
        return

    q = job["queue"]

    try:
        pipe = Pipeline(project_dir=job["output_dir"])

        def status_cb(msg):
            q.put({"event": "status", "data": {"message": msg}})

        pipe.set_status_callback(status_cb)
        jobs.update(job_id, pipeline=pipe, status="running")

        datasheet, match, candidates, suffix_code = pipe.run(part_number, local_pdf=local_pdf)

        jobs.update(
            job_id,
            datasheet=datasheet,
            match=match,
            candidates=candidates,
            suffix_code=suffix_code,
        )

        if datasheet.package is None and len(candidates) > 1:
            # Multiple packages - let user choose before extracting pins
            # Don't auto-select; the frontend will show a package picker
            pass
        elif datasheet.package is None and len(candidates) == 1:
            # Single candidate - auto-select
            best = candidates[0]
            pkg = PackageInfo(
                name=best.name,
                pin_count=best.pin_count,
                ti_code=best.ti_code or "",
            )
            datasheet, match, _, _ = pipe.select_package_and_finish(datasheet, pkg)
            jobs.update(job_id, datasheet=datasheet, match=match)

        # Pipeline complete
        ds_schema = _datasheet_to_schema(datasheet)
        match_schema = _match_to_schema(match)
        pins_data = [p.model_dump() for p in ds_schema.pins]

        jobs.update(job_id, status="complete")
        q.put({
            "event": "complete",
            "data": {
                "datasheet": ds_schema.model_dump(),
                "match": match_schema.model_dump(),
                "pins": pins_data,
                "candidates": [
                    {"name": c.name, "pin_count": c.pin_count, "ti_code": c.ti_code or ""}
                    for c in candidates
                ],
            },
        })

    except Exception as e:
        logger.exception("Pipeline error for job %s", job_id)
        jobs.update(job_id, status="error")
        q.put({"event": "error", "data": {"message": str(e)}})

    q.put(None)  # sentinel


@router.post("/run", response_model=RunResponse, dependencies=[Depends(require_license)])
async def run_pipeline(req: RunRequest, request: Request):
    jobs = _get_jobs(request)
    job_id = jobs.create()

    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, req.part_number, jobs),
        daemon=True,
    )
    thread.start()

    return RunResponse(job_id=job_id)


@router.get("/status/{job_id}")
async def stream_status(job_id: str, request: Request):
    jobs = _get_jobs(request)
    job = jobs.get(job_id)

    if not job:
        return {"error": "Job not found"}

    q = job["queue"]

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, lambda: q.get(timeout=300))
            except Exception:
                break
            if msg is None:
                break
            yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/select-package", response_model=SelectPackageResponse, dependencies=[Depends(require_license)])
async def select_package(req: SelectPackageRequest, request: Request):
    jobs = _get_jobs(request)
    job = jobs.get(req.job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pipe = job.get("pipeline")
    ds = job.get("datasheet")
    if not pipe or not ds:
        raise HTTPException(status_code=400, detail="Pipeline not ready")

    pkg = PackageInfo(
        name=req.package.name,
        pin_count=req.package.pin_count,
        ti_code=req.package.ti_code or "",
    )
    loop = asyncio.get_event_loop()
    datasheet, match, _, _ = await loop.run_in_executor(
        None, lambda: pipe.select_package_and_finish(ds, pkg)
    )
    jobs.update(req.job_id, datasheet=datasheet, match=match)

    ds_schema = _datasheet_to_schema(datasheet)
    match_schema = _match_to_schema(match)

    return SelectPackageResponse(
        datasheet=ds_schema,
        match=match_schema,
        pins=ds_schema.pins,
    )


@router.post("/finalize", response_model=FinalizeResponse, dependencies=[Depends(require_license)])
async def finalize(req: FinalizeRequest, request: Request):
    jobs = _get_jobs(request)
    job = jobs.get(req.job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pipe = job["pipeline"]
    ds = job["datasheet"]
    match = job["match"]

    # Convert schema pins back to PinInfo dataclass
    confirmed_pins = [
        PinInfo(
            number=p.number,
            name=p.name,
            pin_type=p.pin_type,
            description=p.description,
            alt_numbers=p.alt_numbers,
            is_hidden=p.is_hidden,
        )
        for p in req.pins
    ]

    # If a project_dir was provided, save directly to the KiCad project
    imported = False
    if req.project_dir:
        if not os.path.isdir(req.project_dir):
            raise HTTPException(status_code=400, detail=f"Project directory not found: {req.project_dir}")
        pipe.project_dir = req.project_dir
        imported = True

    # Run finalize
    try:
        result = pipe.finalize(ds, match, confirmed_pins)
    except Exception as e:
        logger.exception("finalize failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Build file manifest
    output_dir = req.project_dir if imported else job["output_dir"]
    file_list = []

    # Symbol file
    if result.symbol_lib_path and os.path.isfile(result.symbol_lib_path):
        fname = os.path.basename(result.symbol_lib_path)
        size = os.path.getsize(result.symbol_lib_path)
        file_list.append(FileInfo(filename=fname, size_bytes=size))

    # Footprint files
    if result.footprint_lib_path and os.path.isdir(result.footprint_lib_path):
        for f in os.listdir(result.footprint_lib_path):
            fpath = os.path.join(result.footprint_lib_path, f)
            if os.path.isfile(fpath):
                # Use relative path including the .pretty dir
                rel = os.path.join(os.path.basename(result.footprint_lib_path), f)
                file_list.append(FileInfo(filename=rel, size_bytes=os.path.getsize(fpath)))

    # Build model info
    model_info = None
    if result.model_ref:
        model_info = ModelInfo(ref=result.model_ref, inferred=result.model_ref_inferred)

    return FinalizeResponse(job_id=req.job_id, files=file_list, model=model_info, imported=imported)
