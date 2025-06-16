# main.py  –  Smar# main.py  – PGA-Smart-Quiz bot
import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                            PostbackEvent, QuickReply, QuickReplyButton,
                            PostbackAction)

# ---------- load flow ----------
with open("quiz.yaml", encoding="utf-8") as f:
    raw_nodes = yaml.safe_load(f)

FLOW = {}
for i, n in enumerate(raw_nodes, 1):
    if "id" not in n:                       # ใส่ id อัตโนมัติถ้าไม่มี
        n["id"] = f"Q{i}"
    FLOW[n["id"]] = n

# ---------- LINE / Flask ----------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

State = collections.namedtuple("State", "node picks answers meta")
#   node   = id ปัจจุบัน
#   picks  = นับครั้งกดภายใน node เดียว (ใช้ min_select)
#   answers= dict เก็บผล {id:code}
#   meta   = flag/ตัวแปรเพิ่ม (เกท, highest_level, impact ฯลฯ)
user_state: dict[str, State] = {}

# ---------- helper ----------
def to_quick(items):
    return QuickReply(items=[
        QuickReplyButton(
            action=PostbackAction(
                label=i["label"][:20],                 # LINE จำกัด 20 ตัวอักษร
                data=i.get("next","") or i["code"],    # ส่ง next ถ้ามี ไม่ก็ code
                display_text=i["full"])
        ) for i in items
    ])

def send_q(reply_token, node_id):
    node = FLOW[node_id]
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(node["question"], quick_reply=to_quick(node["quick"]))
    )

def finish(reply_token, msg):
    line_bot_api.reply_message(reply_token, TextSendMessage(msg))

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

# ---------- text ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e: MessageEvent):
    cmd = e.message.text.strip().lower()
    if cmd not in ("เริ่ม", "start", "เริ่มใหม่"):
        line_bot_api.reply_message(
            e.reply_token, TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบสอบถาม'))
        return

    uid = e.source.user_id
    # -------- initialise at Gate-1 --------
    user_state[uid] = State(node="G1", picks=0, answers={}, meta={})
    send_q(e.reply_token, "G1")

# ---------- postback ----------
@handler.add(PostbackEvent)
def on_postback(e: PostbackEvent):
    uid = e.source.user_id
    if uid not in user_state:
        finish(e.reply_token, 'พิมพ์ "เริ่ม" ก่อนนะคะ')
        return

    st   = user_state[uid]
    node = FLOW[st.node]

    data = e.postback.data            # อาจเป็น next หรือ code
    try:
        choice = next(i for i in node["quick"]
                      if i["code"] == data or i.get("next","") == data)
    except StopIteration:
        finish(e.reply_token, "โปรดเลือกจากปุ่มที่กำหนดนะคะ")
        return

    # ----- save answer -----
    answers = dict(st.answers)
    answers[node["id"]] = choice["code"]
    picks   = st.picks + 1
    next_id = choice.get("next") or node.get("next")

    # ----- honor min_select -----
    min_sel = node.get("min_select", 1)
    if picks < min_sel:
        user_state[uid] = State(node=st.node, picks=picks,
                                answers=answers, meta=st.meta)
        send_q(e.reply_token, st.node)
        return

    # ----- finished branch? -----
    if next_id is None:
        finish(e.reply_token, _decide_award(answers))
        user_state.pop(uid, None)
        return

    if next_id not in FLOW:           # safety
        finish(e.reply_token, f"Flow error: ไม่พบ node {next_id}")
        user_state.pop(uid, None)
        return

    # ----- advance -----
    user_state[uid] = State(node=next_id, picks=0,
                            answers=answers, meta=st.meta)
    send_q(e.reply_token, next_id)

# ---------- rule engine ----------
def _decide_award(ans: dict[str,str]) -> str:
    """ยกตัวอย่าง rule คร่าว ๆ – ปรับตาม Blueprint R-codes"""
    got_award = ans.get("Q2")          # A/B/C
    lvl_map   = {"L1":1,"L2":2,"L3":3,"L4":4,"L5":5}
    highest   = lvl_map.get(ans.get("Q3"),0)
    impact    = {"I":1,"II":2,"III":3}.get(ans.get("Q3-a"),1)
    xp        = {"X1","X2"} & set(ans.values())

    if got_award == "A" and highest <= 2:
        return "✅ แนะนำสมัครรางวัล *Open Governance*"
    if got_award == "A" and highest >= 3 and impact >= 2:
        return "✅ แนะนำสมัครรางวัล *Effectiveness of People Participation*"
    if got_award in ("B","C") and "X1" in xp:
        return "✅ แนะนำสมัครรางวัล *เลื่องลือขยายผล – ขยายพื้นที่*"
    if got_award in ("B","C") and "X2" in xp:
        return "✅ แนะนำสมัครรางวัล *เลื่องลือขยายผล – พัฒนาต่อยอด*"
    return "ยังไม่เข้าเกณฑ์รางวัลใด / โปรดปรึกษาทีมงานค่ะ"

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
