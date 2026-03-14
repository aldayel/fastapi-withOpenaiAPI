import json
from http import HTTPStatus

from fastapi import APIRouter
from starlette.responses import Response

from openai_service import process_event
from schemas import EventSchema


router = APIRouter()


"""
Becuase of the router, every endpoint in this file is prefixed with /events/
"""


@router.post("/", dependencies=[])
def handle_event(data: EventSchema) -> Response:
    result = process_event(data)

    return Response(
        content=json.dumps({"message": "Data received!", "response": result}),
        status_code=HTTPStatus.ACCEPTED,
    )
