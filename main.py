# main.py  –  Smart-Quiz bot (PGA)
import os, yaml, collections
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (MessageEvent, TextMessage, TextSendMessage,
                            PostbackEvent, QuickReply, QuickReplyButton,
                            PostbackAction)

# ---------- โหลด flow ----------
with open("quiz.yaml", encoding="utf-8") as f:
    raw_nodes = yaml.safe_load(f)

# map id -> node dict   (เพิ่ม index ให้อัตโนมัติถ้าไม่มี id)
FLOW = {}
for i, n in enumerate(raw_nodes, 1):
    if "id" not in n:
        n["id"] = f"Q{i}"
    FLOW[n["id"]] = n

# ---------- LINE/Flask ----------
app          = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler      = WebhookHandler(os.getenv("CHANNEL_SECRET"))

State = collections.namedtuple("State", "node picks answers meta")
#  meta ใช้เก็บ flag gate / highest_level / impact ฯลฯ
user_state: dict[str, State] = {}

# ---------- helper ----------
def to_quick(items):
    return QuickReply(items=[
        QuickReplyButton(
            action=PostbackAction(
                label=i["label"][:20],          # 20 char limit
                data=i.get("next","") or i["code"],
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

# ---------- ข้อความ ----------
@handler.add(MessageEvent, message=TextMessage)
def on_text(e: MessageEvent):
    command = e.message.text.strip().lower()
    if command not in ("เริ่ม", "start", "เริ่มใหม่"):
        line_bot_api.reply_message(
            e.reply_token, TextSendMessage('พิมพ์ "เริ่ม" เพื่อเริ่มแบบสอบถาม'))
        return

    # reset / init
    uid = e.source.user_id
    user_state[uid] = State(node="Q1", picks=0, answers={}, meta={})
    send_q(e.reply_token, "Q1")

# ---------- Postback ----------
@handler.add(PostbackEvent)
def on_postback(e: PostbackEvent):
    uid = e.source.user_id
    if uid not in user_state:
        finish(e.reply_token, 'พิมพ์ "เริ่ม" ก่อนนะคะ');  return

    st = user_state[uid]
    node = FLOW[st.node]

    # ------ หา choice ที่ user เลือก ------
    # data อาจเป็น next id หรือ code; ตรวจทั้งสอง
    data = e.postback.data
    try:
        choice = next(i for i in node["quick"]
                      if i["code"] == data or i.get("next","") == data)
    except StopIteration:
        finish(e.reply_token, "เลือกจากปุ่มเท่านั้นนะคะ");  return

    # ------ บันทึกคำตอบ ------
    answers = dict(st.answers)
    answers[node["id"]] = choice["code"]

    picks   = st.picks + 1
    next_id = choice.get("next") or node.get("next")

    # ------ ตรวจ min_select ------
    if node.get("min_select", 1) > picks:
        user_state[uid] = State(node=st.node, picks=picks,
                                answers=answers, meta=st.meta)
        send_q(e.reply_token, st.node)
        return

    # ------ ถึง node สิ้นสุด? ------
    if next_id is None:
        result_msg = _decide_award(answers)      # สรุปผลตาม rule
        finish(e.reply_token, result_msg)
        user_state.pop(uid, None)
        return

    # ------ ไป node ถัดไป ------
    if next_id not in FLOW:
        finish(e.reply_token, f"Flow error: ไม่มี node {next_id}")
        user_state.pop(uid, None); return

    user_state[uid] = State(node=next_id, picks=0,
                            answers=answers, meta=st.meta)
    send_q(e.reply_token, next_id)

# ---------- Rule-Engine ----------
def _decide_award(ans: dict[str,str]) -> str:
    """รับ dict {'Q1':'A1', 'Q2':'B0', ... } → คืนผลลัพธ์เป็น string"""
    a = ans.get("Q2")  # เคยได้รางวัลหรือไม่
    lvl = {"C1":1,"C2":2,"C3":3,"C4":4}.get(ans.get("Q3"),0)
    impact = {"I":1,"II":2,"III":3}.get(ans.get("Q3-a"),1)
    xp = {"X1","X2"} & set(ans.values())

    # ตัวอย่าง rule – ปรับให้ตรง table R-xxx
    if a == "A1" and lvl <= 2:
        return "แนะนำสมัครรางวัล *เปิดใจใกล้ชิดประชาชน (Open Governance)*"
    if a == "A1" and lvl >= 3 and impact >= 2:
        return "แนะนำสมัครรางวัล *สัมฤทธิผลประชาชนมีส่วนร่วม*"
    if a in ("B","C") and "X1" in xp:
        return "แนะนำสมัครรางวัล *เลื่องลือขยายผล – ขยายพื้นที่*"
    if a in ("B","C") and "X2" in xp:
        return "แนะนำสมัครรางวัล *เลื่องลือขยายผล – พัฒนาต่อยอด*"
    return "ยังไม่เข้าเกณฑ์รางวัลใด / โปรดปรึกษาทีมงาน"

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
