import asyncio
import json
import logging
import os
import threading
import tempfile
import dataclasses

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
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

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_jobs(request: Request) -> JobStore:
    return request.app.state.jobs


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

        if len(candidates) > 1 and datasheet.package is None:
            # Need user to pick a package
            jobs.update(job_id, status="awaiting_package")
            q.put({
                "event": "package_select",
                "data": {
                    "candidates": [
                        {
                            "name": c.name,
                            "pin_count": c.pin_count,
                            "ti_code": c.ti_code or "",
                        }
                        for c in candidates
                    ]
                },
            })
            # Wait for user to select a package (up to 5 minutes)
            job["package_event"].wait(timeout=300)

            selected = job.get("selected_package")
            if not selected:
                q.put({"event": "error", "data": {"message": "Package selection timed out"}})
                jobs.update(job_id, status="error")
                q.put(None)
                return

            # Run phase 2 with selected package
            pkg = PackageInfo(
                name=selected.name,
                pin_count=selected.pin_count,
                ti_code=selected.ti_code,
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
            },
        })

    except Exception as e:
        logger.exception("Pipeline error for job %s", job_id)
        jobs.update(job_id, status="error")
        q.put({"event": "error", "data": {"message": str(e)}})

    q.put(None)  # sentinel


@router.post("/run", response_model=RunResponse)
async def run_pipeline(request: Request, datasheet: UploadFile = File(...)):
    jobs = _get_jobs(request)
    job_id = jobs.create()

    # Save uploaded PDF to a temp file
    tmp_dir = tempfile.mkdtemp(prefix="schemagic_")
    pdf_path = os.path.join(tmp_dir, datasheet.filename or "datasheet.pdf")
    content = await datasheet.read()
    with open(pdf_path, "wb") as f:
        f.write(content)

    # Derive part number from filename (strip .pdf extension)
    part_number = os.path.splitext(datasheet.filename or "unknown")[0]

    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, part_number, jobs),
        kwargs={"local_pdf": pdf_path},
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


@router.post("/select-package", response_model=SelectPackageResponse)
async def select_package(req: SelectPackageRequest, request: Request):
    jobs = _get_jobs(request)
    job = jobs.get(req.job_id)

    if not job:
        return {"error": "Job not found"}

    # Set the selected package and signal the pipeline thread
    job["selected_package"] = req.package
    job["package_event"].set()

    # Wait for the pipeline thread to finish processing
    q = job["queue"]
    loop = asyncio.get_event_loop()

    # Drain queue until we get the complete event
    while True:
        try:
            msg = await loop.run_in_executor(None, lambda: q.get(timeout=60))
        except Exception:
            break
        if msg is None or msg["event"] in ("complete", "error"):
            break

    # Return current state
    job = jobs.get(req.job_id)
    ds = job["datasheet"]
    match = job["match"]

    ds_schema = _datasheet_to_schema(ds)
    match_schema = _match_to_schema(match)

    return SelectPackageResponse(
        datasheet=ds_schema,
        match=match_schema,
        pins=ds_schema.pins,
    )


@router.post("/finalize", response_model=FinalizeResponse)
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
        )
        for p in req.pins
    ]

    # Run finalize
    import os
    try:
        result = pipe.finalize(ds, match, confirmed_pins)
    except Exception as e:
        logger.exception("finalize failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Build file manifest
    output_dir = job["output_dir"]
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

    return FinalizeResponse(job_id=req.job_id, files=file_list, model=model_info)
