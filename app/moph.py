import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


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
        "cid": str(row["cid"]) if row.get("cid") else "",
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


def build_welcome_payload(row, header="ยินดีต้อนรับ", text="ยินดีต้อนรับสู่โรงพยาบาล", title="ยินดีต้อนรับ"):
    name = " ".join(
        str(x).strip()
        for x in [
            row.get("pname"),
            row.get("fname"),
            row.get("lname")
        ]
        if x
    )

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "ยินดีต้อนรับ",
        "header": header,
        "Text": text,
        "message_title": title,
        "message_html": f"<div><strong>{text} คุณ {name}</strong></div>",
        "message_text": title,
        "message_type": "HPT"
    }


def build_queue_with_url_payload(row, url, header="แจ้งเตือนคิว", text="เช็คสถานะคิวของคุณ", title="แจ้งเตือนคิว"):
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
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "แจ้งเตือนคิว",
        "header": header,
        "queue_no": queue_no,
        "hn_no": str(row["hn"]),
        "service": service,
        "url": url,
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>คิวที่ {queue_no} บริการ {service}</strong><br><a href='{url}'>คลิกเพื่อตรวจสอบคิว</a></div>",
        "message_text": title,
        "message_type": "HPT"
    }


def build_almost_turn_payload(row, queue_waiting, url, header="ใกล้ถึงคิวของคุณแล้ว", text="ใกล้ถึงคิวของคุณแล้ว", title="ใกล้ถึงคิวของคุณแล้ว"):
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
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "ใกล้ถึงคิวของคุณแล้ว",
        "header": header,
        "queue_no": queue_no,
        "queue_waiting": str(queue_waiting),
        "hn_no": str(row["hn"]),
        "service": service,
        "url": url,
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>คิวที่ {queue_no} บริการ {service}</strong><br>รออีก {queue_waiting} คิว<br><a href='{url}'>คลิกเพื่อตรวจสอบคิว</a></div>",
        "message_text": title,
        "message_type": "HPT"
    }

async def send_to_moph(payload):
    """
    ยิง MOPH API และตรวจสอบทั้ง HTTP Status Code และ JSON Response Body
    คืนค่า (is_success, is_permanent_error, http_status_code, moph_code, response_text)
    """
    headers = {
        "Authorization": f"Bearer {settings.moph_access_token}",
        "client-key": settings.moph_client_key,
        "secret-key": settings.moph_secret_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                settings.moph_url,
                json=payload,
                headers=headers
            )

            http_status = response.status_code
            response_text = response.text
            moph_code = None
            is_success = False
            is_permanent_error = False

            # ลอง parse JSON body เพื่อเช็ค message_code ของ MOPH
            try:
                res_json = response.json()
                if isinstance(res_json, dict):
                    moph_code = str(
                        res_json.get("message_code")
                        or res_json.get("code")
                        or res_json.get("status")
                        or ""
                    )
            except Exception:
                res_json = {}

            # เงื่อนไขการตัดสิน Success / Permanent Error:
            # MOPH API บางครั้งส่ง HTTP 200 แต่ใน Body คืน message_code = 401 หรือ credential incorrect
            if response.is_success:
                # ถ้า HTTP 200/2xx และ message_code บ่งบอกว่าสำเร็จ (200, 0, SUCCESS)
                if moph_code in ["200", "0", "SUCCESS", ""] and res_json.get("message_code") != 401:
                    is_success = True
                else:
                    # HTTP 200 แต่ MOPH Body บอกว่า Error (เช่น 401 Unauthorized / Invalid Client Key)
                    is_success = False
                    if moph_code in ["401", "403", "400"] or "incorrect" in response_text.lower():
                        is_permanent_error = True
            else:
                # HTTP Status 4xx (Client Error เช่น Auth พลาด, Bad Request) = Permanent Error (ไม่ต้อง retry)
                if 400 <= http_status < 500:
                    is_permanent_error = True
                # HTTP Status 5xx (Server Error/Gateway Timeout) = Transient Error (ทำ retry ได้)

            return (
                is_success,
                is_permanent_error,
                http_status,
                moph_code,
                response_text
            )

    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
        # Network errors = Transient errors (สามารถ Retry ได้)
        return False, False, None, "NETWORK_ERROR", str(exc)
    except Exception as exc:
        logger.exception("Unexpected error sending to MOPH")
        return False, True, None, "UNKNOWN_ERROR", str(exc)
