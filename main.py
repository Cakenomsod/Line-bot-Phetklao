import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import google.generativeai as genai
from dotenv import load_dotenv

# =========================
# โหลด ENV
# =========================
load_dotenv()

app = Flask(__name__)

# =========================
# โหลด Keys
# =========================
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise ValueError("LINE ENV ไม่ครบ")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# =========================
# โหลดข้อมูล
# =========================
try:
    with open("my_info.txt", "r", encoding="utf-8") as f:
        my_info = f.read()
except:
    my_info = "ไม่มีข้อมูล"

# =========================
# SYSTEM PROMPT
# =========================
SYSTEM_PROMPT = f"""
คุณคือผู้ช่วยส่วนตัวของฟรีแลนซ์คนนึง
ตอบคำถามเกี่ยวกับทักษะ ราคา และการติดต่อเท่านั้น

กฎ:
- ตอบภาษาไทย
- กระชับ เป็นมิตร ไม่เกิน 3-4 ประโยค
- ถ้าลูกค้าสนใจ ให้ชวนคุยต่อเพื่อปิดงาน เช่น:
  - สนใจให้ผมประเมินงานให้ไหมครับ
  - มีตัวอย่างงานไหมครับ เดี๋ยวผมดูให้
- ถ้าถามนอกเหนือจากข้อมูล ให้ตอบว่า "ติดต่อโดยตรงได้เลยนะครับ"

ข้อมูล:
{my_info}
"""

model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# ROUTE TEST
# =========================
@app.route("/")
def home():
    return "BOT IS RUNNING"

# =========================
# CALLBACK
# =========================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid Signature")
        abort(400)
    except Exception as e:
        print("❌ CALLBACK ERROR:", e)
        abort(500)

    return "OK"

# =========================
# Gemini Call
# =========================
def ask_gemini(user_message):
    if not GEMINI_API_KEY:
        return "ตอนนี้ระบบ AI ไม่พร้อมใช้งานครับ ติดต่อโดยตรงได้เลยนะครับ"

    try:
        response = model.generate_content(
            f"{SYSTEM_PROMPT}\n\nลูกค้าถามว่า: {user_message}"
        )

        if not response or not hasattr(response, "text") or not response.text:
            return "ติดต่อโดยตรงได้เลยนะครับ"

        return response.text

    except Exception as e:
        print("❌ GEMINI ERROR:", e)
        return "ขออภัยครับ ระบบมีปัญหาชั่วคราว ติดต่อโดยตรงได้เลยนะครับ"

# =========================
# HANDLE MESSAGE
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text.strip()
    print("👤 USER:", user_message)

    # ✅ เรียก AI ตรง ๆ (ไม่มี quick reply)
    reply_text = ask_gemini(user_message)

    # กันข้อความยาวเกิน
    reply_text = reply_text[:4900]

    print("🤖 BOT:", reply_text)

    # ส่งกลับ LINE
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
    except Exception as e:
        print("❌ LINE ERROR:", e)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))