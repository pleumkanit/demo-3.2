import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import *
from linebot.exceptions import InvalidSignatureError

# ---------- โหลดคำถาม ----------
with open("quiz.yaml", encoding="utf-8") as f:
    QUESTION = yaml.safe_load(f)

app           = Flask(__name__)
line_bot_api  = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler       = WebhookHandler(os.getenv("CHANNEL_SECRET"))
user_state    = {}      # {uid: {"node":id, "tags": Counter()}}

# ---------- helper ----------
def make_qr(node):
    btns = []
    for c in node["choices"]:
        btns.append(
            QuickReplyButton(
                action=PostbackAction(
                    label=c["label"][:20],
                    data=c["label"],              # key เก็บไว้ใน state
                    display_text=c["full"]
                )
            )
        )
    return QuickReply(items=btns)

def send_q(token, uid):
    node = QUESTION[user_state[uid]["node"]]
    line_bot_api.reply_message(token, TextSendMessage(
        text=node["question"],
        quick_reply=make_qr(node)
    ))

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

# ---------- text event ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e: MessageEvent):
    uid = e.source.user_id
    txt = e.message.text.strip().lower()
    if txt in ("เริ่ม","start","reset","เริ่มใหม่"):
        user_state[uid] = {"node":"Q1", "tags": collections.Counter()}
        send_q(e.reply_token, uid)
    else:
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบประเมิน')
        )

# ---------- postback ----------
@handler.add(PostbackEvent)
def on_postback(e: PostbackEvent):
    uid   = e.source.user_id
    label = e.postback.data
    st    = user_state.get(uid)
    if not st:                # ยังไม่กดเริ่ม
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage('พิมพ์ "เริ่ม" ก่อนนะครับ')
        ); return

    node = QUESTION[st["node"]]

    # บันทึก tag / multi
    choice = next(c for c in node["choices"] if c["label"] == label)
    if node.get("multi"):
        tag = choice.get("tag")
        if tag: st["tags"][tag] += 1
        # กดซ้ำไม่ได้ – จบชุด multi เมื่อใช้ label ซ้ำเป็น “ต่อไป” ก็ได้
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage("เลือกได้ครบแล้ว ให้กด \"ถัดไป\" หรือตัวเลือกสรุป")
        )
        return

    # เดินเส้นทาง
    next_id   = choice.get("next")
    result    = choice.get("result")
    if not next_id and not result:
        # กรณี node ใช้ nextMap / resultRules
        if "nextMap" in node:             # กรณี Q3
            for key, nxt in node["nextMap"].items():
                if st["tags"][key] > 0:
                    next_id = nxt; break
        if "resultRules" in node:         # กรณี 4A / 4B ฯลฯ
            cnt = sum(st["tags"].values())
            for cond, msg in node["resultRules"].items():
                if cond.startswith(">=") and cnt >= int(cond[2:]):
                    result = msg; break
            else:
                result = node["resultRules"].get("default")

    if result:          # จบ
        line_bot_api.reply_message(e.reply_token,
            TextSendMessage(f"ผลที่เหมาะสม ➜ {result}")
        )
        user_state.pop(uid, None)
    else:
        st["node"] = next_id
        send_q(e.reply_token, uid)

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
