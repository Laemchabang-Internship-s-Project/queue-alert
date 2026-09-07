import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def get_name(row):
    if row.get("name"):
        return str(row["name"]).strip()
    return " ".join(
        str(x).strip()
        for x in [row.get("pname"), row.get("fname"), row.get("lname")]
        if x
    )


def get_queue_no(row):
    if row.get("queue_no"):
        return str(row["queue_no"]).strip()
    return build_queue_display(row)


def get_service(row):
    if row.get("service"):
        return str(row["service"]).strip()
    category = row.get("category_name") or ""
    room = row.get("room_name") or row.get("room_code") or ""
    return f"{category} ห้อง {room}".strip()


def get_hn(row):
    return str(row.get("hn_no") or row.get("hn") or "")


def build_queue_display(row):
    """
    รวม category_name + qnumber เป็นเลขคิวแสดงผล เช่น 'หมอพร้อม-10'
    """
    category = (row.get("category_name") or "").strip()
    qnumber = str(row.get("qnumber") or "").strip()
    if category:
        return f"{category}-{qnumber}"
    return qnumber


def build_welcome_payload(
    row,
    header="ยินดีต้อนรับ",
    text="สวัสดีครับ ยินดีต้อนรับสู่บริการสุขภาพ เราใส่ใจในสุขภาพและความสบายใจของคุณทุกขั้นตอน หากมีข้อสงสัยหรือสิ่งใดที่เราสามารถช่วยเหลือได้ กรุณาแจ้งเจ้าหน้าที่ได้เลยนะครับ",
    title="ยินดีต้อนรับ",
):
    """
    API 1: ยินดีต้อนรับ (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "ยินดีต้อนรับ",
        "header": header,
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>{text}</strong></div>",
        "message_text": title,
        "message_type": "HPT",
    }


def build_payload(row):
    """
    API 2: แจ้งเตือนคิว (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)
    queue_no = get_queue_no(row)
    service = get_service(row)
    hn_no = get_hn(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "แจ้งเตือนคิว",
        "header": "แจ้งเตือนคิว",
        "queue_no": queue_no,
        "hn_no": hn_no,
        "service": service,
        "url": "",
        "message_title": "แจ้งเตือนคิว",
        "message_html": f"<div><strong>คิวที่ {queue_no} บริการ {service}</strong></div>",
        "message_text": "แจ้งเตือนคิว",
        "message_type": "HPT",
    }


def build_queue_with_url_payload(
    row, url, header="แจ้งเตือนคิว", text="เช็คสถานะคิวของคุณ", title="แจ้งเตือนคิว"
):
    """
    API 3: แจ้งเตือนคิว แบบมี url (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)
    queue_no = get_queue_no(row)
    service = get_service(row)
    hn_no = get_hn(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "แจ้งเตือนคิว",
        "header": header,
        "queue_no": queue_no,
        "hn_no": hn_no,
        "service": service,
        "url": url,
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>คิวที่ {queue_no} บริการ {service} ตรวจสอบคิวที่ {url}</strong></div>",
        "message_text": title,
        "message_type": "HPT",
    }


def build_almost_turn_payload(
    row,
    queue_waiting,
    url="",
    header="ใกล้ถึงคิวของคุณแล้ว",
    text="ใกล้ถึงคิวของคุณแล้ว",
    title="ใกล้ถึงคิวของคุณแล้ว",
):
    """
    API 4: ใกล้ถึงคิวของคุณแล้ว (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)
    queue_no = get_queue_no(row)
    service = get_service(row)
    hn_no = get_hn(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "ใกล้ถึงคิวของคุณแล้ว",
        "header": header,
        "queue_no": queue_no,
        "queue_waiting": str(queue_waiting),
        "hn_no": hn_no,
        "service": service,
        "message_title": title,
        "message_html": f"<div><strong>รออีก {queue_waiting} คิว คิวที่ {queue_no} บริการ {service}</strong></div>",
        "message_text": title,
        "message_type": "HPT",
    }


def build_queue_changed_payload(
    row,
    queue_waiting,
    header="คิวของท่านมีการเปลี่ยนแปลง",
    text="คิวของท่านมีการเปลี่ยนแปลง",
    title="คิวของท่านมีการเปลี่ยนแปลง",
):
    """
    API 5: คิวของท่านมีการเปลี่ยนแปลง (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)
    queue_no = get_queue_no(row)
    service = get_service(row)
    hn_no = get_hn(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "คิวของท่านมีการเปลี่ยนแปลง",
        "header": header,
        "queue_no": queue_no,
        "queue_waiting": str(queue_waiting),
        "hn_no": hn_no,
        "service": service,
        "url": "",
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>คิวของท่านมีการเปลี่ยนแปลง คิวที่ {queue_no} บริการ {service}</strong></div>",
        "message_text": title,
        "message_type": "HPT",
    }


def build_queue_changed_with_url_payload(
    row,
    queue_waiting,
    url,
    header="คิวของท่านมีการเปลี่ยนแปลง",
    text="คิวของท่านมีการเปลี่ยนแปลง",
    title="คิวของท่านมีการเปลี่ยนแปลง",
):
    """
    API 6: คิวของท่านมีการเปลี่ยนแปลง แบบมี url (ตาม Spec MOPH V3.1)
    """
    name = get_name(row)
    queue_no = get_queue_no(row)
    service = get_service(row)
    hn_no = get_hn(row)

    return {
        "cid": str(row["cid"]) if row.get("cid") else "",
        "name": name,
        "template": "คิวของท่านมีการเปลี่ยนแปลง",
        "header": header,
        "queue_no": queue_no,
        "queue_waiting": str(queue_waiting),
        "hn_no": hn_no,
        "service": service,
        "url": url,
        "text": text,
        "message_title": title,
        "message_html": f"<div><strong>คิวของท่านมีการเปลี่ยนแปลง คิวที่ {queue_no} บริการ {service} ตรวจสอบคิวล่าสุดที่ {url}</strong></div>",
        "message_text": title,
        "message_type": "HPT",
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
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.post(
                settings.moph_url, json=payload, headers=headers
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
            if response.is_success:
                if (
                    moph_code in ["200", "0", "SUCCESS", ""]
                    and res_json.get("message_code") != 401
                ):
                    is_success = True
                else:
                    is_success = False
                    if (
                        moph_code in ["401", "403", "400"]
                        or "incorrect" in response_text.lower()
                    ):
                        is_permanent_error = True
            else:
                if 400 <= http_status < 500:
                    is_permanent_error = True

            return (
                is_success,
                is_permanent_error,
                http_status,
                moph_code,
                response_text,
            )

    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
        return False, False, None, "NETWORK_ERROR", str(exc)
    except Exception as exc:
        logger.exception("Unexpected error sending to MOPH")
        return False, True, None, "UNKNOWN_ERROR", str(exc)
