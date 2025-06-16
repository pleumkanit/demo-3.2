import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

### ------ โหลดคำถาม ------
with open("quiz.yaml", encoding="utf-8") as f:
    data = yaml.safe_load(f)
    # รองรับทั้ง list และ dict
    if isinstance(data, list):
        QUESTIONS = {item["id"]: item for item in data}
    else:
        QUESTIONS = data         # เป็น dict อยู่แล้ว

### ------ LINE ------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

user_state = {}                  # {uid: {"node": id}}

def make_qr(items):
    return QuickReply(items=[
        QuickReplyButton(action=PostbackAction(
            label=i['label'][:20],
            data=i['code'],
            display_text=i['full']))
        for i in items
    ])

@app.route("/callback", methods=["POST"])
def callback():
    sig  = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def on_text(e):
    uid = e.source.user_id
    if e.message.text.strip().lower() in ("เริ่ม", "start", "เริ่มใหม่"):
        user_state[uid] = {"node": "Q1"}
        send_q(e.reply_token, uid)
    else:
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มทำแบบสอบถาม'))

@handler.add(PostbackEvent)
def on_postback(e):
    uid = e.source.user_id
    st  = user_state.get(uid)
    if not st:
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มทำแบบสอบถาม'))
        return

    # หา next id จาก code ที่ผู้ใช้กด
    next_id = e.postback.data          # เช่น  "Q2", "END"
    if next_id == "END":
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage("แบบสอบถามเสร็จสิ้น ขอบคุณค่ะ"))
        user_state.pop(uid, None)
        return

    st["node"] = next_id
    send_q(e.reply_token, uid)

def send_q(token, uid):
    key  = user_state[uid]["node"]
    node = QUESTIONS.get(key)
    if not node:
        line_bot_api.reply_message(token,
            TextSendMessage(f"ไม่พบคำถาม {key}"))
        user_state.pop(uid, None)
        return

    line_bot_api.reply_message(token, TextSendMessage(
        node["question"],
        quick_reply=make_qr(node["quick"])
    ))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
