import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

with open("quiz.yaml", encoding="utf-8") as f:
    FLOW = yaml.safe_load(f)          # dict keyed by node id

def quick(items):
    return QuickReply(items=[QuickReplyButton(
        action=PostbackAction(
            label=i["label"][:20],
            data=i.get("next",""),                # next node (อาจว่าง)
            display_text=i["full"]))              # echo เต็ม
        for i in items ])

app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

State = collections.namedtuple("State", "node picks tags")   # picks = cnt
user_state: dict[str, State] = {}

# ---------- util ----------
def send_q(token, node_id):
    node = FLOW[node_id]
    line_bot_api.reply_message(
        token,
        TextSendMessage(node["question"], quick_reply=quick(node["quick"]))
    )

def finish(token, msg):
    line_bot_api.reply_message(token, TextSendMessage(msg))

# ---------- webhook ----------
@app.route("/callback", methods=["POST"])
def callback():
    sig  = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ---------- text ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e):
    if e.message.text.strip().lower() not in ("เริ่ม","start","เริ่มใหม่"):
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบสอบถาม'))
        return
    uid = e.source.user_id
    user_state[uid] = State(node="Q1", picks=0, tags=[])
    send_q(e.reply_token, "Q1")

# ---------- postback ----------
@handler.add(PostbackEvent)
def on_postback(e):
    uid = e.source.user_id
    if uid not in user_state:
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" ก่อนนะคะ'));  return

    st = user_state[uid]
    node = FLOW[st.node]
    choice = next(ch for ch in node["quick"]
                  if ch["label"][:20] == e.postback.data or
                     ch.get("next","") == e.postback.data)

    # เก็บ tag / นับจำนวนที่เลือก
    tags = st.tags + [choice["tag"]]
    picks = st.picks + 1

    # หาปลายทาง
    next_node = choice.get("next") or node.get("next")
    if "min_select" in node and picks < node["min_select"]:
        # ยังต้องเลือกต่อ — อยู่ node เดิม
        user_state[uid] = State(node=st.node, picks=picks, tags=tags)
        send_q(e.reply_token, st.node)
        return

    if next_node is None and "end" not in node:
        finish(e.reply_token, "❓  flow ผิดพลาด ไม่รู้จะไปไหนต่อ")
        user_state.pop(uid, None)
        return

    if next_node and next_node in FLOW:
        user_state[uid] = State(node=next_node, picks=0, tags=tags)
        send_q(e.reply_token, next_node)
        return

    # ---- ถึง node จบ ----
    end_msg = FLOW[next_node]["end"] if next_node else node["end"]
    finish(e.reply_token, end_msg)
    user_state.pop(uid, None)

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
