# ---------- main.py ----------
import os, yaml
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextMessage, MessageEvent, TextSendMessage,
    PostbackEvent, PostbackAction,
    QuickReply, QuickReplyButton
)

# ---------- โหลดคำถาม ----------
with open("quiz.yaml", encoding="utf-8") as f:
    QUESTION_LIST = yaml.safe_load(f)          # list[dict]

# ---------- LINE ----------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

user_state: dict[str, int] = {}                # {uid: index}

# ---------- helper ----------
def make_quick(items):
    """รับ list[{label, full}] → QuickReply"""
    return QuickReply(items=[
        QuickReplyButton(
            action=PostbackAction(
                label=i["label"][:20],         # LINE จำกัด 20 ตัวอักษร
                data="next",                   # ไม่ใช้ branch จึงส่งเหมือนกันทุกปุ่ม
                display_text=i["full"]
            )
        ) for i in items
    ])

def send_question(reply_token: str, idx: int):
    q = QUESTION_LIST[idx]
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(q["question"], quick_reply=make_quick(q["quick"]))
    )

# ---------- webhook ----------
@app.route("/callback", methods=["POST"])
def callback():
    sig  = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ---------- รับข้อความ ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e: MessageEvent):
    uid = e.source.user_id
    if e.message.text.strip().lower() in ("เริ่ม", "start", "เริ่มใหม่"):
        user_state[uid] = 0
        send_question(e.reply_token, 0)
    else:
        line_bot_api.reply_message(
            e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มทำแบบสอบถาม')
        )

# ---------- รับ postback ----------
@handler.add(PostbackEvent)
def on_postback(e: PostbackEvent):
    uid = e.source.user_id
    idx = user_state.get(uid, -1)
    if idx == -1:
        line_bot_api.reply_message(
            e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มทำแบบสอบถาม')
        )
        return

    idx += 1
    if idx >= len(QUESTION_LIST):
        line_bot_api.reply_message(
            e.reply_token,
            TextSendMessage("แบบสอบถามเสร็จสิ้น — ขอบคุณค่ะ")
        )
        user_state.pop(uid, None)
    else:
        user_state[uid] = idx
        send_question(e.reply_token, idx)

# ---------- run บน Render ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
