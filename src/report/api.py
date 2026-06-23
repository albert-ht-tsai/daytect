from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from src.core.deps import CurrentUser, SessionDep
from src.device.services.device_service import get_owned_device
from src.report.schemas.report_schema import CreateReportTaskRequest
from src.report.services import report_service

router = APIRouter(tags=["report"])


@router.post("/reports/{device_id}/tasks", status_code=201)
def create_report_task_endpoint(
    device_id: int,
    body: CreateReportTaskRequest,
    db: SessionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
):
    device = get_owned_device(db, current_user, device_id)
    data = report_service.create_task(db, device, body, background_tasks)
    return {"success": True, "data": data, "message": "Report task created successfully."}


@router.get("/reports/{device_id}/tasks/{report_task_id}/progress")
def get_report_task_progress_endpoint(device_id: int, report_task_id: str, db: SessionDep, current_user: CurrentUser):
    device = get_owned_device(db, current_user, device_id)
    data = report_service.get_progress(db, device, report_task_id)
    return {"success": True, "data": data, "message": "Report task progress retrieved successfully."}


@router.get("/reports/{device_id}/tasks/{report_task_id}/result")
def get_report_task_result_endpoint(device_id: int, report_task_id: str, db: SessionDep, current_user: CurrentUser):
    device = get_owned_device(db, current_user, device_id)
    task = report_service.get_task_for_result(db, device, report_task_id)

    if task.status == "completed":
        data = report_service.build_result_body(task)
        return {"success": True, "data": data, "message": "Final report result retrieved successfully."}

    if task.status == "failed":
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": {
                    "report_task_id": task.report_task_id,
                    "status": task.status,
                    "failed_step": task.failed_step,
                    "error_code": task.error_code,
                    "error_message": task.error_message,
                },
                "message": "Report generation failed.",
            },
        )

    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "data": {
                "status": task.status,
                "progress": {
                    "percentage": task.progress_percentage,
                    "completed_batches": task.completed_batches,
                    "total_batches": task.total_batches,
                },
            },
            "message": "Report is still processing.",
        },
    )


@router.post("/reports/{device_id}/tasks/{report_task_id}/retry")
def retry_report_task_endpoint(
    device_id: int, report_task_id: str, db: SessionDep, current_user: CurrentUser, background_tasks: BackgroundTasks
):
    device = get_owned_device(db, current_user, device_id)
    data = report_service.retry_task(db, device, report_task_id, background_tasks)
    return {"success": True, "data": data, "message": "Report task retry started successfully."}
