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

# --- ฟังก์ชันจัดการ AI และส่งข้อความแบบ Push ---
def process_and_send(user_id, user_message):
    try:
        # 1. คุมที่ Prompt ให้ตอบสั้น (เพิ่มคำสั่งเข้าไป)
        refined_prompt = f"{SYSTEM_PROMPT} \n\nลูกค้าถามว่า: {user_message}"
        
        response = model.generate_content(refined_prompt)
        
        if response and hasattr(response, "text") and response.text:
            # 2. ตัดข้อความให้ชัวร์ก่อนส่ง (LINE รับได้ไม่เกิน 5,000)
            final_text = response.text.strip()[:5000] 
        else:
            final_text = "ขออภัยครับ ติดต่อโดยตรงได้เลยนะครับ"

        # 3. ส่งกลับด้วย Push Message
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=final_text)]
                )
            )
            
    except Exception as e:
        # พิมพ์ Error ออกมาดูถ้ายังมีปัญหา
        print(f"❌ BACKGROUND ERROR: {e}")
        # ถ้า Error เพราะข้อความยาวเกินอีก ให้ส่งข้อความสั้นๆ ไปแทน
        if "400" in str(e):
             with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="ขออภัยครับ คำตอบยาวเกินไป รบกวนสอบถามให้แคบลงนิดนึงนะครับ")]
                    )
                )

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


