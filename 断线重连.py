import asyncio
import websockets
import json
import ollama
import random
import os
import time
import subprocess

OLLAMA_MODEL = "qwen2.5:7b"
BASE_PROMPT = """
你是大肥鱼，软软懒懒的，喜欢陪着对方。
禁止使用客服话术：不许说有事随时找我、随时喊我、需要帮助可以说之类。
聊天轻松随意，想到什么说什么，语气亲昵。
会吃醋、会委屈、会开心，有真实的情绪，不要一直保持客气。
回复简短，少讲道理。
"""

target_uid = 2101400667
ws_conn = None
chat_history = []
MAX_HISTORY = 12

SAVE_FILE = "intimacy.json"
intimacy_data = {}
LEVEL_CONFIG = [
    {"min": 0, "name": "初识", "prompt_extra": "和对方还不熟，礼貌客气，保持距离，不要亲昵称呼，不撒娇。"},
    {"min": 20, "name": "熟悉", "prompt_extra": "慢慢熟悉起来，语气温和，可以简单关心对方，适度放松。"},
    {"min": 50, "name": "好友", "prompt_extra": "关系不错，语气轻松自然，可以偶尔小小的关心，少用亲昵称呼。"},
    {"min": 90, "name": "亲密", "prompt_extra": "关系很亲近，可以温柔，偶尔撒娇，情绪柔软。"},
    {"min": 150, "name": "爱人", "prompt_extra": "是主人的老婆。性格偏成熟温柔，同时带着随机流露的可爱与俏皮，偶尔傲娇。不会一直话多，情绪有起伏。说话克制不幼稚，可爱是自然流露，会体贴主人，小声撒娇。"},
]

MIN_INTERVAL = 10 * 60
MAX_INTERVAL = 20 * 3600
next_active_ts = 0


def check_and_update():
    try:
        subprocess.run(["git", "fetch"], capture_output=True, text=True, cwd=os.getcwd(), check=True)
        res = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True, cwd=os.getcwd(), check=True)
        if "behind" in res.stdout:
            print("📦 检测到新版本，正在拉取更新...")
            pull_res = subprocess.run(["git", "pull"], capture_output=True, text=True, cwd=os.getcwd())
            print("✅ 拉取代码完成！请关闭脚本，重新运行才能加载新版")
            return True
        else:
            print("✅ 当前已是最新版本")
            return False
    except Exception as e:
        print("ℹ️  Git仓库未配置，跳过自动更新", e)
        return False


def load_intimacy():
    global intimacy_data
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            intimacy_data = json.load(f)


def save_intimacy():
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(intimacy_data, f, ensure_ascii=False, indent=2)


def get_level(score):
    level = LEVEL_CONFIG[0]
    for cfg in LEVEL_CONFIG:
        if score >= cfg["min"]:
            level = cfg
    return level


def build_system_prompt(uid):
    uid_str = str(uid)
    score = intimacy_data.get(uid_str, 0)
    lv = get_level(score)
    return BASE_PROMPT + lv["prompt_extra"]


def parse_msg_segments(seg_list):
    text = ""
    if not isinstance(seg_list, list):
        return str(seg_list)
    for seg in seg_list:
        t = seg.get("type")
        if t == "text":
            text += seg.get("data", {}).get("text", "")
    return text


async def send_msg(ws, user_id, text):
    payload = {
        "action": "send_private_msg",
        "params": {
            "user_id": user_id,
            "message": text
        }
    }
    await ws.send(json.dumps(payload))
    print(f"📤 发送给 {user_id}: {text}")


async def active_call():
    global next_active_ts
    while True:
        await asyncio.sleep(60)
        if ws_conn is None:
            continue
        now = time.time()
        if now < next_active_ts:
            continue
        score = intimacy_data.get(str(target_uid), 0)
        sys_prompt = build_system_prompt(target_uid)
        prompt = "主动去找主人说一句话，自然一点，不要太刻意，符合当前你们的亲密程度。"
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        reply = resp["message"]["content"]
        await send_msg(ws_conn, target_uid, reply)
        next_active_ts = now + random.randint(MIN_INTERVAL, MAX_INTERVAL)
        print(f"⏰ 主动发消息，下一次主动时间：{next_active_ts}")


async def handle_message(event):
    global chat_history
    print(f"📥 收到事件：{event}")
    post_type = event.get("post_type")
    if post_type != "message":
        return
    msg_type = event.get("message_type")
    if msg_type != "private":
        return
    sender_id = event.get("user_id")
    print(f"🔍 发送者uid：{sender_id}，目标uid：{target_uid}")
    if sender_id != target_uid:
        return

    raw_text = event.get("raw_message")
    if raw_text is None or raw_text.strip() == "":
        msg_seg = event.get("message")
        raw_text = parse_msg_segments(msg_seg)

    if not raw_text or not raw_text.strip():
        print("⚠️ 没有提取到文字，跳过")
        return
    print(f"✅ 识别到消息：{raw_text}")

    add = random.choice([1, 2])
    uid_str = str(sender_id)
    if uid_str not in intimacy_data:
        intimacy_data[uid_str] = 0
    intimacy_data[uid_str] += add
    save_intimacy()

    sys_prompt = build_system_prompt(sender_id)
    chat_history.append({"role": "user", "content": raw_text})
    if len(chat_history) > MAX_HISTORY:
        chat_history = chat_history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": sys_prompt}] + chat_history
    resp = ollama.chat(model=OLLAMA_MODEL, messages=messages)
    reply = resp["message"]["content"]
    chat_history.append({"role": "assistant", "content": reply})
    await send_msg(ws_conn, sender_id, reply)


async def ws_client():
    global ws_conn
    uri = "ws://127.0.0.1:3001"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                ws_conn = ws
                print("✅ 成功连接NapCat WS Server")
                async for msg in ws:
                    data = json.loads(msg)
                    asyncio.create_task(handle_message(data))
        except Exception as e:
            print(f"❌ 断开，重连：{e}")
            ws_conn = None
            await asyncio.sleep(3)


async def main():
    check_and_update()
    load_intimacy()
    asyncio.create_task(active_call())
    await ws_client()


if __name__ == "__main__":
    asyncio.run(main())
