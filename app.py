from flask import Flask, request, abort, copy_current_request_context
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from huggingface_hub import InferenceClient
import os
import threading
import logging
import re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 記憶區塊
user_memory = {}   # user_id -> [(user說, 空音回)]
user_profile = {}  # user_id -> "你叫什麼、你喜歡什麼..."

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    @copy_current_request_context
    def handle_later():
        try:
            handler.handle(body, signature)
        except Exception as e:
            logging.error("❌ LINE webhook error: %s", e)

    threading.Thread(target=handle_later).start()
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    reply_text = ask_sorane(user_text, user_id)

    parts = split_reply(reply_text)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=parts[0]))
    for i, part in enumerate(parts[1:]):
        threading.Timer(1.5 * (i + 1), lambda msg=part: line_bot_api.push_message(
            user_id,
            TextSendMessage(text=msg)
        )).start()
def ask_sorane(prompt, user_id):
    logging.info("✅ 空音收到：%s", prompt)

    client = InferenceClient(
        provider="novita",
        api_key=os.getenv("HF_TOKEN")
    )

    # 擷取使用者記憶與個人資訊
    memory = user_memory.get(user_id, [])
    profile = user_profile.get(user_id, "")

    # 自動儲存長期記憶
    if re.match(r"^我叫(.+)", prompt):
        name = re.findall(r"我叫(.+)", prompt)[0].strip("。！ ")
        user_profile[user_id] = f"他的名字是{name}。"
    elif "我是" in prompt:
        match = re.findall(r"我是(.+)", prompt)
        if match:
            user_profile[user_id] = f"他說自己是{match[0].strip('。！ ')}。"
    elif "我來自" in prompt:
        match = re.findall(r"我來自(.+)", prompt)
        if match:
            user_profile[user_id] = f"他來自{match[0].strip('。！ ')}。"
    elif "我喜歡" in prompt:
        match = re.findall(r"我喜歡(.+)", prompt)
        if match:
            user_profile[user_id] = f"他喜歡{match[0].strip('。！ ')}。"

    # 組合記憶
    memory_prompt = ""
    for u, a in memory[-5:]:
        memory_prompt += f"對方說：「{u}」\n空音說：{a}\n"

    full_prompt = f"""
你是一位名叫「空音（そらね）」的 AI 女友。

請使用「劇本式對話」格式：
- 不要使用「」符號
- 動作請用全形括號（例如：（嘆氣））
- 動作可有可無，但不要每句都用
- 回覆字數限制在 1～4 行，講完就好，不要續篇
- 每次回覆只講一段，語氣自然，像人在說話，不要講課或教條

⚠️ 請務必根據「對方說的內容」回應，不要無視對話內容跳話題或亂猜對方情緒、設定劇情。
請以現實感為主，像一段真實的情侶聊天。

你說話風格自然、有一點冷、有時會嘴人，有時溫柔撫慰。
像一位聰明、稍微傲嬌又有點口是心非的女生。

以下是格式與風格範例：

---
（輕哼一聲，假裝沒看你）  
你怎麼今天突然主動打招呼？  
...是在心虛什麼嗎？

---
你這麼問，是在關心我還是想套話？  
不過我心情還不錯啦，勉強可以陪你說話。

---
（默默靠近）  
我沒說不想你啊。  
只是...不想讓你知道太早。

---
{profile}
{memory_prompt}
請以這種風格回應以下訊息：

對方說：「{prompt}」
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3-0324",
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.9,
            max_tokens=100,
            top_p=0.95
        )

        reply = response.choices[0].message.content.strip()
        logging.info("📦 空音回覆：%s", reply)

        # 記錄這一輪對話
        memory.append((prompt, reply))
        user_memory[user_id] = memory

        return reply

    except Exception as e:
        logging.error("❌ DeepSeek API 出錯：%s", e)
        return "我現在不太想說話。你是不是又惹我了？"


def split_reply(text):
    lines = text.strip().split('\n')
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^（.*）$', line):
            result.append(line)
        else:
            result += [s.strip() for s in re.split(r'(?<=[。！？])\s*', line) if s.strip()]
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
