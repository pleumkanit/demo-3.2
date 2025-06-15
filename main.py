import os, yaml
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, PostbackAction,
    QuickReply, QuickReplyButton
)

# --- load questions from yaml ---
with open("quiz.yaml", encoding="utf-8") as f:
    QUESTIONS = yaml.safe_load(f)

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

user_state = {}  # {uid: idx}

def make_qr(items):
    return QuickReply(items=[
        QuickReplyButton(action=PostbackAction(label=i['label'][:20], data=i['code'], display_text=i['full']))
        for i in items
    ])

@app.route("/callback", methods=["POST"])
def callback():
    sig = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    uid = event.source.user_id
    txt = event.message.text.strip().lower()
    if txt in ("เริ่ม","เริ่มใหม่","start"):
        user_state[uid] = 0
        ask_question(event.reply_token, uid)
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่ม'))

@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    idx = user_state.get(uid, 0)
    idx += 1
    if idx >= len(QUESTIONS):
        line_bot_api.reply_message(event.reply_token, TextSendMessage("แบบสอบถามจบแล้ว ขอบคุณค่ะ"))
        user_state.pop(uid, None)
    else:
        user_state[uid] = idx
        ask_question(event.reply_token, uid)

def ask_question(token, uid):
    q = QUESTIONS[user_state[uid]]
    line_bot_api.reply_message(token, TextSendMessage(
        q['question'], quick_reply=make_qr(q['quick'])
    ))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
