import asyncio
import logging
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import settings
from app.moph import (
    build_payload,
    build_welcome_payload,
    build_queue_with_url_payload,
    build_almost_turn_payload,
    build_queue_changed_payload,
    build_queue_changed_with_url_payload,
    send_to_moph
)
from app.postgres import (
    init_db,
    record_notification_start,
    update_notification_result,
    get_notification_stats,
    get_recent_notifications
)
from app.worker import queue_worker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    worker = asyncio.create_task(queue_worker())
    yield
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="NEOQ → MOPH Alert Console",
    version="1.3.0",
    lifespan=lifespan
)


class TestSendRequest(BaseModel):
    template_type: str  # welcome, queue_created, queue_created_url, almost_turn, queue_changed, queue_changed_url
    cid: str
    pname: Optional[str] = "นาย"
    fname: Optional[str] = "ทดสอบ"
    lname: Optional[str] = "แจ้งเตือน"
    hn: Optional[str] = "65-001234"
    category_name: Optional[str] = "แผนกผู้ป่วยนอก"
    qnumber: Optional[str] = "A001"
    room_name: Optional[str] = "ห้องตรวจ 1"
    queue_waiting: Optional[int] = 2
    url: Optional[str] = "https://morprom.moph.go.th"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    data = await get_notification_stats()
    return {"status": "ok", "data": data}


@app.get("/notifications")
async def notifications(limit: int = Query(default=50, ge=1, le=200)):
    items = await get_recent_notifications(limit=limit)
    return {"status": "ok", "count": len(items), "data": items}


@app.post("/api/test-send")
async def test_send_notification(req: TestSendRequest):
    """
    API สำหรับยิงทดสอบ MOPH Alert ด้วยข้อมูลจำลอง/ข้อมูลจริง
    """
    vn = f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}"
    row = {
        "vn": vn,
        "hn": req.hn,
        "cid": req.cid,
        "pname": req.pname,
        "fname": req.fname,
        "lname": req.lname,
        "qnumber": req.qnumber,
        "category_name": req.category_name,
        "room_name": req.room_name,
        "room_code": req.room_name,
        "date": datetime.now().date(),
        "time": datetime.now().time(),
    }

    url = req.url or settings.queue_tracking_url or "https://morprom.moph.go.th"

    if req.template_type == "welcome":
        payload = build_welcome_payload(row)
    elif req.template_type == "queue_created_url":
        payload = build_queue_with_url_payload(row, url=url)
    elif req.template_type == "almost_turn":
        payload = build_almost_turn_payload(row, queue_waiting=req.queue_waiting, url=url)
    elif req.template_type == "queue_changed":
        payload = build_queue_changed_payload(row, queue_waiting=req.queue_waiting)
    elif req.template_type == "queue_changed_url":
        payload = build_queue_changed_with_url_payload(row, queue_waiting=req.queue_waiting, url=url)
    else:  # queue_created
        payload = build_payload(row)

    is_success, is_perm, http_status, moph_code, res_text = await send_to_moph(payload)

    # บันทึกผลลง Postgres
    notif_type = f"test_{req.template_type}"
    data = {
        "vn": vn,
        "queue_date": row["date"],
        "queue_no": req.qnumber or "A001",
        "cid": req.cid,
        "patient_name": f"{req.pname} {req.fname} {req.lname}".strip(),
        "hn_no": req.hn,
        "service": f"{req.category_name} ห้อง {req.room_name}",
        "notification_type": notif_type
    }
    await record_notification_start(data)
    await update_notification_result(
        vn=vn,
        notification_type=notif_type,
        success=is_success,
        is_permanent_error=is_perm,
        response_status=http_status,
        moph_code=moph_code,
        response_body=res_text
    )

    return {
        "status": "ok",
        "is_success": is_success,
        "is_permanent_error": is_perm,
        "http_status": http_status,
        "moph_code": moph_code,
        "payload": payload,
        "response_text": res_text
    }


@app.get("/", response_class=HTMLResponse)
async def test_dashboard():
    """
    หน้าเว็บแดชบอร์ดทดสอบยิง MOPH Alert (พร้อมระบบ Passcode Protection)
    """
    html_content = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEOQ → MOPH Alert Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Prompt', sans-serif; background: #0f172a; color: #f8fafc; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.1); }
        .card-active { border-color: #3b82f6 !important; background: rgba(59, 130, 246, 0.15) !important; }
    </style>
</head>
<body class="min-h-screen pb-12">

    <!-- Passcode Protection Modal Overlay -->
    <div id="auth-modal" class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/90 backdrop-blur-md p-4">
        <div class="glass max-w-md w-full p-8 rounded-3xl border border-slate-700/80 shadow-2xl text-center">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white font-bold text-3xl mx-auto mb-4 shadow-lg shadow-blue-500/30">
                🔒
            </div>
            <h2 class="text-xl font-bold text-white mb-2">กรอกรหัสผ่านเพื่อเข้าใช้งาน</h2>
            <p class="text-xs text-slate-400 mb-6">กรุณากรอกรหัสผ่านยืนยันตัวตนก่อนเข้าสู่หน้า Console</p>
            
            <div class="space-y-4">
                <div>
                    <input type="password" id="auth-password" placeholder="กรอกรหัสผ่านที่นี่..." class="w-full px-4 py-3 bg-slate-900 border border-slate-700 rounded-xl text-center text-white text-base focus:outline-none focus:border-blue-500 font-mono tracking-widest" onkeyup="if(event.key==='Enter') checkAuth()">
                    <p id="auth-error" class="text-xs text-rose-400 mt-2 hidden">⚠️ รหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง</p>
                </div>
                <button onclick="checkAuth()" class="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-xl transition shadow-lg shadow-blue-500/25">
                    เข้าสู่ระบบ
                </button>
            </div>
        </div>
    </div>

    <!-- Main Content (Hidden until authenticated) -->
    <div id="main-app" class="hidden">
        <!-- Navbar -->
        <header class="glass sticky top-0 z-50 px-6 py-4 mb-8 border-b border-slate-800">
            <div class="max-w-7xl mx-auto flex justify-between items-center">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white font-bold text-xl shadow-lg shadow-blue-500/30">
                        Q
                    </div>
                    <div>
                        <h1 class="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">NEOQ → MOPH Alert</h1>
                        <p class="text-xs text-blue-400 font-medium">Interactive Test Console</p>
                    </div>
                </div>
                <div class="flex items-center space-x-3">
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse"></span>
                        Running
                    </span>
                    <button onclick="logout()" class="px-3 py-1.5 text-xs bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded-lg transition border border-rose-500/20">
                        🚪 ออกจากระบบ
                    </button>
                </div>
            </div>
        </header>

        <div class="max-w-7xl mx-auto px-4 sm:px-6">
            <!-- Dashboard Summary Stats -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
                <div class="glass p-4 rounded-2xl">
                    <p class="text-xs text-slate-400 mb-1">คิวทั้งหมดวันนี้</p>
                    <h3 id="stat-total" class="text-2xl font-bold text-white">0</h3>
                </div>
                <div class="glass p-4 rounded-2xl">
                    <p class="text-xs text-slate-400 mb-1">ยินดีต้อนรับ/คิวใหม่</p>
                    <h3 id="stat-created" class="text-2xl font-bold text-blue-400">0</h3>
                </div>
                <div class="glass p-4 rounded-2xl">
                    <p class="text-xs text-slate-400 mb-1">ใกล้ถึงคิว</p>
                    <h3 id="stat-almost" class="text-2xl font-bold text-amber-400">0</h3>
                </div>
                <div class="glass p-4 rounded-2xl">
                    <p class="text-xs text-slate-400 mb-1">ส่งสำเร็จ (SENT)</p>
                    <h3 id="stat-sent" class="text-2xl font-bold text-emerald-400">0</h3>
                </div>
                <div class="glass p-4 rounded-2xl">
                    <p class="text-xs text-slate-400 mb-1">ล้มเหลว (FAILED)</p>
                    <h3 id="stat-failed" class="text-2xl font-bold text-rose-400">0</h3>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
                <!-- Left Form Side -->
                <div class="lg:col-span-6 space-y-6">
                    <div class="glass p-6 rounded-3xl">
                        <h2 class="text-base font-semibold mb-4 text-slate-200">
                            ⚙️ ป้อนข้อมูลทดสอบยิง MOPH Alert (Manual)
                        </h2>

                        <!-- Template Selector Grid -->
                        <label class="block text-xs text-slate-400 font-medium mb-2">เลือก Template ที่ต้องการทดสอบ (6 แบบ):</label>
                        <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6" id="template-grid">
                            <div onclick="selectTemplate('welcome')" id="tmpl-welcome" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs card-active">
                                <span class="font-semibold text-blue-400 block mb-1">1. ยินดีต้อนรับ</span>
                                <span class="text-[10px] text-slate-400">ข้อความต้อนรับเข้าบริการ</span>
                            </div>
                            <div onclick="selectTemplate('queue_created')" id="tmpl-queue_created" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs">
                                <span class="font-semibold text-emerald-400 block mb-1">2. แจ้งเตือนคิว</span>
                                <span class="text-[10px] text-slate-400">แจ้งเลขคิวและห้องตรวจ</span>
                            </div>
                            <div onclick="selectTemplate('queue_created_url')" id="tmpl-queue_created_url" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs">
                                <span class="font-semibold text-indigo-400 block mb-1">3. แจ้งคิว (มี URL)</span>
                                <span class="text-[10px] text-slate-400">แจ้งคิวพร้อมแนบลิงก์</span>
                            </div>
                            <div onclick="selectTemplate('almost_turn')" id="tmpl-almost_turn" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs">
                                <span class="font-semibold text-amber-400 block mb-1">4. ใกล้ถึงคิว</span>
                                <span class="text-[10px] text-slate-400">แจ้งจำนวนคิวรอ</span>
                            </div>
                            <div onclick="selectTemplate('queue_changed')" id="tmpl-queue_changed" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs">
                                <span class="font-semibold text-purple-400 block mb-1">5. คิวเปลี่ยน</span>
                                <span class="text-[10px] text-slate-400">แจ้งเตือนเปลี่ยนคิว</span>
                            </div>
                            <div onclick="selectTemplate('queue_changed_url')" id="tmpl-queue_changed_url" class="glass p-3 rounded-xl cursor-pointer border border-slate-700 hover:border-blue-500 transition text-xs">
                                <span class="font-semibold text-pink-400 block mb-1">6. คิวเปลี่ยน (URL)</span>
                                <span class="text-[10px] text-slate-400">แจ้งย้ายห้องพร้อมลิงก์</span>
                            </div>
                        </div>

                        <!-- Manual Input Fields -->
                        <div class="space-y-4">
                            <div>
                                <label class="block text-xs text-slate-400 mb-1">CID (เลขบัตรประชาชน 13 หลัก) <span class="text-blue-400">*ใส่เพื่อทดสอบรับ LINE</span></label>
                                <input type="text" id="input-cid" placeholder="กรอกเลข CID 13 หลัก..." class="w-full px-4 py-2.5 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-blue-500">
                            </div>
                            <div class="grid grid-cols-3 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">คำนำหน้า</label>
                                    <input type="text" id="input-pname" value="นาย" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">ชื่อ</label>
                                    <input type="text" id="input-fname" value="ทดสอบ" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">นามสกุล</label>
                                    <input type="text" id="input-lname" value="แจ้งเตือน" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                            </div>

                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">เลข HN</label>
                                    <input type="text" id="input-hn" value="65-001234" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">เลขคิว (Queue No)</label>
                                    <input type="text" id="input-qnumber" value="A001" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                            </div>

                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">แผนกบริการ</label>
                                    <input type="text" id="input-category" value="แผนกผู้ป่วยนอก" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">ห้องตรวจ</label>
                                    <input type="text" id="input-room" value="ห้องตรวจ 1" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                            </div>

                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">จำนวนคิวรอ</label>
                                    <input type="number" id="input-waiting" value="2" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                                <div>
                                    <label class="block text-xs text-slate-400 mb-1">URL เช็คคิว (ถ้ามี)</label>
                                    <input type="text" id="input-url" value="https://morprom.moph.go.th" class="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-white">
                                </div>
                            </div>

                            <button onclick="sendTestNotification()" id="btn-send" class="w-full mt-4 py-3.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold rounded-2xl shadow-lg shadow-blue-500/25 transition duration-200 flex items-center justify-center space-x-2">
                                <span>🚀 ยิง MOPH Alert ตอนนี้</span>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Right JSON Inspector Side -->
                <div class="lg:col-span-6 space-y-6">
                    <div class="glass p-6 rounded-3xl h-full flex flex-col justify-between">
                        <div>
                            <h2 class="text-base font-semibold mb-3 text-slate-200 flex items-center justify-between">
                                <span>📦 JSON Payload ที่ส่งไปยัง MOPH</span>
                                <span id="send-status-badge" class="hidden text-xs px-2.5 py-0.5 rounded-full font-semibold"></span>
                            </h2>
                            <pre id="payload-container" class="bg-slate-950 p-4 rounded-2xl border border-slate-800 text-xs font-mono text-blue-300 min-h-[380px] overflow-x-auto">
{
  "info": "รอกรอกข้อมูลและกดปุ่มยิงเพื่อดู JSON Payload..."
}
                            </pre>
                        </div>
                    </div>
                </div>
            </div>

            <!-- History Log Table -->
            <div class="glass p-6 rounded-3xl mt-8">
                <h2 class="text-base font-semibold mb-4 text-slate-200 flex items-center justify-between">
                    <span>📋 ประวัติการยิงแจ้งเตือนล่าสุด</span>
                    <button onclick="fetchNotifications()" class="text-xs text-blue-400 hover:underline">รีเฟรชตาราง</button>
                </h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse text-xs">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-400">
                                <th class="py-3 px-4">VN / เวลา</th>
                                <th class="py-3 px-4">ประเภท</th>
                                <th class="py-3 px-4">ผู้ป่วย</th>
                                <th class="py-3 px-4">คิว / บริการ</th>
                                <th class="py-3 px-4">สถานะ</th>
                            </tr>
                        </thead>
                        <tbody id="logs-tbody" class="divide-y divide-slate-800/50 text-slate-300">
                            <tr>
                                <td colspan="5" class="py-6 text-center text-slate-500">กำลังโหลดประวัติ...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        const AUTH_KEY = 'EA0010823';
        let selectedTemplate = 'welcome';

        function checkAuth() {
            const pass = document.getElementById('auth-password').value;
            if (pass === AUTH_KEY) {
                sessionStorage.setItem('console_authed', 'true');
                document.getElementById('auth-modal').classList.add('hidden');
                document.getElementById('main-app').classList.remove('hidden');
                fetchStats();
                fetchNotifications();
            } else {
                document.getElementById('auth-error').classList.remove('hidden');
            }
        }

        function logout() {
            sessionStorage.removeItem('console_authed');
            location.reload();
        }

        // Auto auth check on load
        if (sessionStorage.getItem('console_authed') === 'true') {
            document.getElementById('auth-modal').classList.add('hidden');
            document.getElementById('main-app').classList.remove('hidden');
        }

        function selectTemplate(type) {
            selectedTemplate = type;
            document.querySelectorAll('#template-grid > div').forEach(div => {
                div.classList.remove('card-active');
            });
            document.getElementById('tmpl-' + type).classList.add('card-active');
        }

        async function fetchStats() {
            try {
                const res = await fetch('/stats');
                const json = await res.json();
                if (json.data) {
                    document.getElementById('stat-total').innerText = json.data.total_today || 0;
                    document.getElementById('stat-created').innerText = json.data.created_count || 0;
                    document.getElementById('stat-almost').innerText = json.data.almost_turn_count || 0;
                    document.getElementById('stat-sent').innerText = json.data.sent_count || 0;
                    document.getElementById('stat-failed').innerText = json.data.failed_count || 0;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchNotifications() {
            try {
                const res = await fetch('/notifications?limit=20');
                const json = await res.json();
                const tbody = document.getElementById('logs-tbody');
                if (json.data && json.data.length > 0) {
                    tbody.innerHTML = json.data.map(item => {
                        const statusClass = item.status === 'SENT' 
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                            : 'bg-rose-500/10 text-rose-400 border-rose-500/20';
                        return `
                            <tr class="hover:bg-slate-900/50 transition">
                                <td class="py-3 px-4">
                                    <div class="font-medium text-white">${item.vn}</div>
                                    <div class="text-[10px] text-slate-500">${new Date(item.created_at).toLocaleTimeString()}</div>
                                </td>
                                <td class="py-3 px-4 font-mono text-[11px] text-blue-400">${item.notification_type}</td>
                                <td class="py-3 px-4 font-medium text-white">${item.patient_name || '-'}</td>
                                <td class="py-3 px-4">
                                    <span class="font-semibold text-white">${item.queue_no}</span>
                                    <span class="text-slate-400 text-[11px]">(${item.service || '-'})</span>
                                </td>
                                <td class="py-3 px-4">
                                    <span class="px-2.5 py-1 text-[10px] font-semibold rounded-full border ${statusClass}">
                                        ${item.status}
                                    </span>
                                </td>
                            </tr>
                        `;
                    }).join('');
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-slate-500">ไม่พบประวัติการยิงวันนี้</td></tr>`;
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function sendTestNotification() {
            const cid = document.getElementById('input-cid').value.trim();
            if (!cid) {
                alert('กรุณากรอกเลข CID 13 หลักก่อนสั่งยิงครับ');
                return;
            }

            const btn = document.getElementById('btn-send');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ กำลังยิง MOPH Alert...</span>';

            const payloadData = {
                template_type: selectedTemplate,
                cid: cid,
                pname: document.getElementById('input-pname').value.trim(),
                fname: document.getElementById('input-fname').value.trim(),
                lname: document.getElementById('input-lname').value.trim(),
                hn: document.getElementById('input-hn').value.trim(),
                category_name: document.getElementById('input-category').value.trim(),
                qnumber: document.getElementById('input-qnumber').value.trim(),
                room_name: document.getElementById('input-room').value.trim(),
                queue_waiting: parseInt(document.getElementById('input-waiting').value) || 0,
                url: document.getElementById('input-url').value.trim()
            };

            try {
                const res = await fetch('/api/test-send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadData)
                });
                const json = await res.json();

                // Show payload and badge
                document.getElementById('payload-container').innerHTML = JSON.stringify(json.payload, null, 2);

                const badge = document.getElementById('send-status-badge');
                badge.classList.remove('hidden', 'bg-emerald-500/20', 'text-emerald-400', 'bg-rose-500/20', 'text-rose-400');
                if (json.is_success) {
                    badge.classList.add('bg-emerald-500/20', 'text-emerald-400');
                    badge.innerText = `HTTP ${json.http_status} - SENT SUCCESS`;
                } else {
                    badge.classList.add('bg-rose-500/20', 'text-rose-400');
                    badge.innerText = `HTTP ${json.http_status || 'ERROR'} - FAILED`;
                }

                // Refresh history
                fetchStats();
                fetchNotifications();

            } catch (err) {
                alert('เกิดข้อผิดพลาดในการยิง API: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span>🚀 ยิง MOPH Alert ตอนนี้</span>';
            }
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
