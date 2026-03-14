import os

from openai import OpenAI

from schemas import EventSchema


def process_event(data: EventSchema) -> str:
    """Process event by sending the message to OpenAI and returning the response."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    message = data.event_data.get("message", "")
    if not message:
        return "No message provided in event_data."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": message},
        ],
    )

    return response.choices[0].message.content or ""
