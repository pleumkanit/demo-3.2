# main.py
import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (QuickReply, QuickReplyButton, PostbackAction,
                            TextSendMessage, MessageEvent, TextMessage,
                            PostbackEvent)

# ---------- โหลด flow ----------
with open("quiz.yaml", encoding="utf-8") as f:
    raw = yaml.safe_load(f)

# ถ้า yaml เป็น list → แปลงเป็น dict keyed by id
if isinstance(raw, list):
    FLOW = {n["id"]: n for n in raw}
else:
    FLOW = raw                      # เป็น dict อยู่แล้ว

# ---------- helper ----------
def make_qr(items):
    """สร้าง QuickReply  (label ถูกตัด ≤20 ตัวอักษรตามข้อกำหนด LINE)"""
    return QuickReply(items=[
        QuickReplyButton(action=PostbackAction(
            label=i["label"][:20],
            data=i.get("next", i["label"]),      # ส่งอะไรไปก็ได้ ขอให้ไม่เกิน 300 byte
            display_text=i["full"]))
        for i in items
    ])

State = collections.namedtuple("State", "node picks tags")
user_state: dict[str, State] = {}    # เก็บสถานะแต่ละ uid

def send_q(token, node_id):
    node = FLOW[node_id]
    line_bot_api.reply_message(
        token,
        TextSendMessage(node["question"],
                        quick_reply=make_qr(node["quick"]))
    )

def finish(token, msg):
    line_bot_api.reply_message(token, TextSendMessage(msg))

# ---------- LINE setup ----------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

@app.route("/callback", methods=["POST"])
def callback():
    sig  = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ---------- Event: ข้อความ ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e):
    txt = e.message.text.strip().lower()
    if txt not in ("เริ่ม", "start", "เริ่มใหม่"):
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบสอบถาม'))
        return

    uid = e.source.user_id
    user_state[uid] = State(node="Q1", picks=0, tags=[])
    send_q(e.reply_token, "Q1")

# ---------- Event: Postback ----------
@handler.add(PostbackEvent)
def on_postback(e):
    uid = e.source.user_id
    if uid not in user_state:
        finish(e.reply_token, 'พิมพ์ "เริ่ม" ก่อนนะคะ');  return

    st   = user_state[uid]
    node = FLOW[st.node]

    # หา choice ที่กด (จาก data หรือ label 20 ตัวแรก)
    choice = next((c for c in node["quick"]
                   if c.get("next","") == e.postback.data
                   or c["label"][:20]   == e.postback.data), None)

    if not choice:                        # safety guard
        finish(e.reply_token, "ไม่พบตัวเลือกนี้");  return

    # ---------------- update state ----------------
    tags  = st.tags + [choice["tag"]]
    picks = st.picks + 1

    # ถ้า node กำหนดว่าต้องเลือกอย่างน้อยกี่ข้อ
    if node.get("min_select", 1) > picks:
        user_state[uid] = State(node=st.node, picks=picks, tags=tags)
        send_q(e.reply_token, st.node)
        return

    # ---------------- ไป node ถัดไป ----------------
    next_id = choice.get("next") or node.get("next")

    # case 1: ยังมี node ถัดไป
    if next_id and next_id in FLOW:
        user_state[uid] = State(node=next_id, picks=0, tags=tags)
        send_q(e.reply_token, next_id)
        return

    # case 2: ถึง node จบ (มี key end)
    end_msg = (FLOW[next_id]["end"] if next_id else node.get("end"))
    if end_msg:
        finish(e.reply_token, end_msg)
    else:
        finish(e.reply_token, "แบบสอบถามเสร็จสิ้น")

    user_state.pop(uid, None)    # ล้าง state

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
