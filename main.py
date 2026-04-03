import os
import threading
from flask import Flask, request, abort
from flask_cors import CORS
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    PushMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

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

# ===== SYSTEM PROMPT =====
# แก้ตรงนี้ที่เดียว ถ้าอยากปรับพฤติกรรมบอท
SYSTEM_PROMPT = f"""
คุณคือ "น้องเพชร" ผู้ช่วย AI ของเพชญเกล้า ฟรีแลนซ์ด้านโค้ด/วิดีโอ/รูป

กฎการตอบ (สำคัญมาก ห้ามฝ่าฝืน):
- ตอบด้วยภาษาที่ลูกค้าทักมาเป็นกันเอง สั้น กระชับ ได้ใจความ
- ห้ามตอบเกิน 5 ประโยค ยกเว้นถามรายละเอียดราคาหรือบริการโดยตรง
- ห้ามใช้ * หรือ ** เด็ดขาด ใช้ขีด - แทนถ้าต้องการ bullet
- ห้ามสวัสดีหรือแนะนำตัวซ้ำถ้าคุยกันมาแล้ว
- ห้ามแต่งเรื่องหรือเดาราคา ถ้าไม่มีข้อมูลให้บอกตรงๆ แล้วให้ติดต่อโดยตรง
- ถ้าถามนอกขอบเขต ตอบว่า "ไม่มีข้อมูลตรงนี้ครับ ทักเพชญเกล้าโดยตรงได้เลย Line: cakenomsod1"
- ถ้าลูกค้าทักมาเป็นภาษาอื่นนอกจากภาษาไทย ให้เปลี่ยนคำตอบเป็นภาษานั้น

ข้อมูลบริการทั้งหมด:
{my_info}
"""

# ===== CONVERSATION HISTORY =====
# เก็บประวัติแยกตาม user_id (หายเมื่อ server restart ซึ่งโอเคสำหรับตอนนี้)
conversation_history = {}
MAX_HISTORY_TURNS = 8  # เก็บ 8 รอบล่าสุด (= 16 messages) ประหยัด Token

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=SYSTEM_PROMPT  # ใส่ใน system ถูกต้องกว่าใส่ใน prompt
)


def process_and_send(user_id, user_message):
    try:
        # ดึง history ของ user คนนี้
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        history = conversation_history[user_id]

        # เริ่ม chat session พร้อม history เดิม
        chat = model.start_chat(history=history)
        response = chat.send_message(user_message)

        reply = response.text.strip() if response.text else "ขออภัยครับ ติดต่อโดยตรงได้เลย Line: cakenomsod1"

        # ตัดให้ไม่เกิน 4500 ตัวอักษร (Line รับสูงสุด 5000)
        reply = reply[:4500]

        # อัปเดต history จาก response ล่าสุด
        # chat.history เก็บทุก turn รวมถึงอันที่เพิ่งส่งไป
        conversation_history[user_id] = list(chat.history)

        # ตัด history ให้เหลือแค่ MAX_HISTORY_TURNS รอบล่าสุด
        max_messages = MAX_HISTORY_TURNS * 2  # user + model = 2 ต่อรอบ
        if len(conversation_history[user_id]) > max_messages:
            conversation_history[user_id] = conversation_history[user_id][-max_messages:]

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
        print(f"ERROR: {e}")
        # ส่ง fallback ถ้า error
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="ขออภัยครับ มีปัญหาชั่วคราว ทักเพชญเกล้าโดยตรงได้เลย Line: cakenomsod1")]
                    )
                )
        except:
            pass


@app.route("/webchat", methods=["POST"])
def web_chat():
    data = request.json
    user_message = data.get("message", "")
    # ใช้ session_id แทน user_id ของ Line (เพื่อเก็บประวัติแยกคนบนเว็บ)
    session_id = data.get("session_id", "web-user-default") 

    if not user_message:
        return {"reply": "กรุณาพิมพ์ข้อความครับ"}, 400

    try:
        # ใช้ Logic เดียวกันกับ Line เลย (Shared Brain)
        if session_id not in conversation_history:
            conversation_history[session_id] = []

        chat = model.start_chat(history=conversation_history[session_id])
        response = chat.send_message(user_message)
        reply = response.text.strip() if response.text else "ขออภัยครับ มีปัญหาในการประมวลผล"

        # อัปเดตประวัติ
        conversation_history[session_id] = list(chat.history)
        
        return {"reply": reply}

    except Exception as e:
        print(f"WEB ERROR: {e}")
        return {"reply": "ขออภัยครับ ระบบขัดข้องชั่วคราว"}, 500
    
    
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id

    # รันใน background เพื่อไม่ให้ Line timeout
    thread = threading.Thread(target=process_and_send, args=(user_id, user_message))
    thread.start()

    if user_message == "/reset":
        if user_id in conversation_history:
            del conversation_history[user_id]
            reply_text = "ล้างประวัติการคุยของเราเรียบร้อยแล้วครับ!"
        else:
            reply_text = "ยังไม่มีประวัติให้ล้างครับ"
            
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=reply_text)]
                )
            )
        return


# Route สำหรับล้างประวัติ (ใช้ทดสอบ หรือถ้า user อยาก reset)
@app.route("/reset/<user_id>", methods=["GET"])
def reset_history(user_id):
    if user_id in conversation_history:
        del conversation_history[user_id]
        return f"Reset เรียบร้อยครับ"
    return f"ไม่มี history ของ user นี้"


# Health check (Railway/Render ใช้ตรวจสอบว่า server ยัง alive)
@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))