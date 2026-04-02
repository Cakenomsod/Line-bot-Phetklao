import os
import threading  # เพิ่มเข้ามาเพื่อทำ Background Task
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    PushMessageRequest, TextMessage  # เปลี่ยนจาก Reply เป็น Push
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# โหลดข้อมูล
try:
    with open("my_info.txt", "r", encoding="utf-8") as f:
        my_info = f.read()
except:
    my_info = "ไม่มีข้อมูล"

SYSTEM_PROMPT = f"{my_info}"
model = genai.GenerativeModel("gemini-2.5-flash")

# เก็บประวัติแยกตาม user_id
conversation_history = {}
MAX_HISTORY = 10  # เก็บแค่ 10 รอบล่าสุด ประหยัด Token


# --- ฟังก์ชันจัดการ AI และส่งข้อความแบบ Push ---
def process_and_send(user_id, user_message):
    try:
        # ดึงประวัติของ user คนนี้ ถ้าไม่มีสร้างใหม่
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        history = conversation_history[user_id]

        # เพิ่มข้อความใหม่เข้าไป
        history.append({
            "role": "user",
            "parts": [user_message]
        })

        # ส่งพร้อม History ทั้งหมด
        chat = model.start_chat(history=history[:-1])
        response = chat.send_message(
            f"{SYSTEM_PROMPT}\n\nลูกค้าถามว่า: {user_message}"
            if len(history) == 1
            else user_message
        )

        reply = response.text.strip()[:4500] if response.text else "ติดต่อโดยตรงได้เลยครับ 😊"

        # เพิ่ม Reply ของ AI เข้า History
        history.append({
            "role": "model",
            "parts": [reply]
        })

        # ตัดให้เหลือแค่ MAX_HISTORY รอบ
        if len(history) > MAX_HISTORY * 2:
            conversation_history[user_id] = history[-(MAX_HISTORY * 2):]

        # ส่งกลับ Line
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=reply)]
                )
            )

    except Exception as e:
        print(f"❌ ERROR: {e}")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK" # ตอบกลับ LINE ทันทีเพื่อป้องกัน Timeout

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id # เก็บ ID ไว้ส่ง Push กลับ

    # สั่งให้ทำงานเบื้องหลังแล้วจบฟังก์ชันนี้ทันที
    thread = threading.Thread(target=process_and_send, args=(user_id, user_message))
    thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


@app.route("/reset/<user_id>", methods=["GET"])
def reset_history(user_id):
    if user_id in conversation_history:
        del conversation_history[user_id]
    return f"Reset history for {user_id}"