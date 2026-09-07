import httpx
from app.config import settings


def build_payload(row):
    name = " ".join(
        str(x).strip()
        for x in [
            row.get("pname"),
            row.get("fname"),
            row.get("lname")
        ]
        if x
    )

    queue_no = str(row["qnumber"])
    category = row.get("category_name") or ""
    room = row.get("room_code") or ""
    service = f"{category} ห้อง {room}".strip()

    return {
        "cid": str(row["cid"]),
        "name": name,
        "template": "แจ้งเตือนคิว",
        "header": "แจ้งเตือนคิว",
        "queue_no": queue_no,
        "hn_no": str(row["hn"]),
        "service": service,
        "url": "",
        "message_title": "แจ้งเตือนคิว",
        "message_html": f"<div><strong>คิวที่ {queue_no} บริการ {service}</strong></div>",
        "message_text": "แจ้งเตือนคิว",
        "message_type": "HPT"
    }


async def send_to_moph(payload):
    headers = {
        "Authorization": f"Bearer {settings.moph_access_token}",
        "client-key": settings.moph_client_key,
        "secret-key": settings.moph_secret_key,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds
    ) as client:
        response = await client.post(
            settings.moph_url,
            json=payload,
            headers=headers
        )
        return (
            response.status_code,
            response.text,
            response.is_success
        )
