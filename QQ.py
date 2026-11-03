import requests
import json
import websocket
import time
import threading
import random
from datetime import datetime

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "deepseek-r1:7b"
NAPCAT_HTTP = "http://127.0.0.1:3000"
NAPCAT_WS = "ws://127.0.0.1:3001"
MY_QQ = 2101400667

def gen_ai_text(prompt):
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_gpu": 20, "num_ctx": 2048}
    }
    r = requests.post(OLLAMA_URL, json=payload)
    content = r.json()["message"]["content"]
    if "" in content:
        content = content.split("")[-1].strip()
    return content

def send_private_msg(qq, text):
    res = requests.post(f"{NAPCAT_HTTP}/send_private_msg", json={
        "user_id": qq,
        "message": text
    })
    print(f"[主动私聊]发给{qq}：{text}")

def send_qzone(content):
    res = requests.post(f"{NAPCAT_HTTP}/send_qzone_msg", json={
        "content": content,
        "ugc_right": 1
    })
    print(f"[发空间] {content}")

def is_active_time():
    h = datetime.now().hour
    return 8 <= h <= 23

def random_behavior_loop():
    while True:
        sleep_sec = random.randint(6*60, 25*60)
        time.sleep(sleep_sec)
        if not is_active_time():
            continue
        roll_do_something = random.random()
        if roll_do_something < 0.4:
            print("[随机行为]本轮不想说话，跳过")
            continue
        act = random.choices(["chat", "qzone"], weights=[0.65, 0.35])[0]
        if act == "chat":
            prompt = """按照你的人设，主动开启一段私聊对话，简短自然，像现实朋友找你搭话，不要思考标签，不要长篇大论。"""
            msg = gen_ai_text(prompt)
            send_private_msg(MY_QQ, msg)
        elif act == "qzone":
            prompt = """生成一条简短生活化QQ空间说说，情绪自然，不要思考标记，不要太长。"""
            sp_text = gen_ai_text(prompt)
            send_qzone(sp_text)

def on_message(ws, data):
    d = json.loads(data)
    if d.get("post_type") == "message" and d.get("message_type") == "group":
        raw = d["raw_message"]
        gid = d["group_id"]
        if raw.startswith("ai "):
            txt = raw.removeprefix("ai ")
            res_text = gen_ai_text(txt)
            send_data = {"action": "send_group_msg", "params": {"group_id": gid, "message": res_text}}
            ws.send(json.dumps(send_data))

if __name__ == "__main__":
    behavior_thread = threading.Thread(target=random_behavior_loop, daemon=True)
    behavior_thread.start()
    ws = websocket.WebSocketApp(NAPCAT_WS, on_message=on_message)
    ws.run_forever()
