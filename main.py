import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Load Keys
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# โหลดข้อมูลของคุณ
with open("my_info.txt", "r", encoding="utf-8") as f:
    my_info = f.read()

# System Prompt
SYSTEM_PROMPT = f"""
คุณคือผู้ช่วยส่วนตัวของฟรีแลนซ์คนนึง
ตอบคำถามเกี่ยวกับทักษะ ราคา และการติดต่อเท่านั้น
ตอบภาษาไทย กระชับ เป็นมิตร ไม่เกิน 3-4 ประโยค
ถ้าถามนอกเหนือจากข้อมูล ให้บอกว่า "ติดต่อโดยตรงได้เลยนะครับ"

ข้อมูล:
{my_info}
"""

model = genai.GenerativeModel("gemini-2.5-flash-lite-preview-06-17" )

@app.route("/")
def home():
    return "RUNNING OK"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text

    # ส่งไป Gemini
    response = model.generate_content(
        f"{SYSTEM_PROMPT}\n\nลูกค้าถามว่า: {user_message}"
    )

    reply_text = response.text

    # ตอบกลับ Line
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))