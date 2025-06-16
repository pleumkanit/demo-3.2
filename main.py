# main.py  (แก้ version)
import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

# ---------- โหลด flow ----------
with open("quiz.yaml", encoding="utf-8") as f:
    FLOW = {n["id"]: n for n in yaml.safe_load(f)}

def make_quick(btns):
    """สร้าง quick-reply ให้ถูกเกณฑ์ (label ≤20)"""
    return QuickReply(items=[
        QuickReplyButton(
            action=PostbackAction(
                label=item["label"][:20],
                data=item.get("next", ""),           # ส่ง next node (อาจว่าง)
                display_text=item["full"]))
        for item in btns
    ])

# ---------- LINE objects ----------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

State = collections.namedtuple("State", "node picks codes")
user_state: dict[str, State] = {}        # {uid: State}

# ---------- helper ----------
def send_q(token: str, node_id: str):
    node = FLOW[node_id]
    line_bot_api.reply_message(
        token,
        TextSendMessage(node["question"], quick_reply=make_quick(node["quick"]))
    )

def finish(token: str, msg: str):
    line_bot_api.reply_message(token, TextSendMessage(msg))

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

# ---------- เริ่มต้นด้วยข้อความ ----------
@handler.add(MessageEvent, message=TextMessage)
def handle_text(e: MessageEvent):
    txt = e.message.text.strip().lower()
    if txt not in ("เริ่ม", "start", "เริ่มใหม่"):
        line_bot_api.reply_message(
            e.reply_token, TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบสอบถาม'))
        return

    uid = e.source.user_id
    user_state[uid] = State(node="Q1", picks=0, codes=[])
    send_q(e.reply_token, "Q1")

# ---------- postback ----------
@handler.add(PostbackEvent)
def handle_postback(e: PostbackEvent):
    uid = e.source.user_id
    if uid not in user_state:
        line_bot_api.reply_message(
            e.reply_token, TextSendMessage('พิมพ์ "เริ่ม" ก่อนนะคะ'))
        return

    st   = user_state[uid]
    node = FLOW[st.node]

    # หา choice ที่ผู้ใช้เลือก
    data = e.postback.data
    try:
        choice = next(c for c in node["quick"]
                      if c.get("next", "") == data or c["label"][:20] == data)
    except StopIteration:
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage("⚠️ เลือกตัวเลือกไม่ถูกต้อง ลองใหม่อีกครั้ง"))
        return

    codes = st.codes + [choice["code"]]
    picks = st.picks + 1
    next_node = choice.get("next") or node.get("next")  # อาจว่าง

    # --- ยังเลือกไม่ครบตาม min_select ---
    if node.get("min_select") and picks < node["min_select"]:
        user_state[uid] = State(node=st.node, picks=picks, codes=codes)
        send_q(e.reply_token, st.node)
        return

    # --- ไป node ถัดไป ---
    if next_node and next_node in FLOW:
        user_state[uid] = State(node=next_node, picks=0, codes=codes)
        send_q(e.reply_token, next_node)
        return

    # --- node จบ ---
    end_msg = FLOW[next_node]["end"] if next_node else node.get("end")
    if end_msg:
        finish(e.reply_token, end_msg)
    else:
        finish(e.reply_token, "⚠️ flow ผิดพลาด ไม่พบข้อความจบ")
    user_state.pop(uid, None)

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
