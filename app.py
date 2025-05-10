from flask import Flask, request, abort, copy_current_request_context
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from huggingface_hub import InferenceClient
import os
import threading
import logging
import re
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

user_memory = {}     # user_id -> [(你說, 空音回)]
user_profile = {}    # user_id -> { name: ..., likes: [...], location: ..., tags: [...] }

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

    # 自動抽取記憶資訊（AI 推理）
    extract_profile_info(user_text, user_id)

    reply_text = ask_sorane(user_text, user_id)
    parts = split_reply(reply_text)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=parts[0]))
    for i, part in enumerate(parts[1:]):
        threading.Timer(1.5 * (i + 1), lambda msg=part: line_bot_api.push_message(
            user_id,
            TextSendMessage(text=msg)
        )).start()

def extract_profile_info(message, user_id):
    profile = user_profile.setdefault(user_id, {"name": "", "likes": [], "location": "", "tags": []})
    prompt = f"""
以下是一段使用者的訊息，請從中抽取對他個人相關的資訊，像是：名字、喜好、所在地、身分、情緒、目標等。
請用 JSON 格式輸出，欄位有：name、likes、location、tags（皆為字串或字串列表），沒有的請空白或為空陣列。

訊息如下：
「{message}」
    """
    try:
        client = InferenceClient(provider="novita", api_key=os.getenv("HF_TOKEN"))
        res = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3-0324",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        result = json.loads(res.choices[0].message.content.strip())
        if result.get("name"):
            profile["name"] = result["name"]
        for like in result.get("likes", []):
            if like not in profile["likes"]:
                profile["likes"].append(like)
        if result.get("location"):
            profile["location"] = result["location"]
        for tag in result.get("tags", []):
            if tag not in profile["tags"]:
                profile["tags"].append(tag)
    except Exception as e:
        logging.warning("記憶抽取失敗：%s", e)


def ask_sorane(prompt, user_id):
    logging.info("✅ 空音收到：%s", prompt)

    memory = user_memory.get(user_id, [])
    profile = user_profile.setdefault(user_id, {"name": "", "likes": [], "location": "", "tags": []})

    memory_prompt = "".join([
        f"對方說：「{u}」\n空音說：{a}\n"
        for u, a in memory[-5:]
    ])

    profile_text = ""
    if profile["name"]:
        profile_text += f"他的名字是{profile['name']}。\n"
    if profile["location"]:
        profile_text += f"他來自{profile['location']}。\n"
    if profile["likes"]:
        profile_text += f"他喜歡：{', '.join(profile['likes'])}。\n"
    if profile["tags"]:
        profile_text += f"目前標記：{', '.join(profile['tags'])}。\n"

    full_prompt = f"""
你是一位名叫「空音（そらね）」的女友。

請使用「劇本式對話」格式：
- 必須使用繁體中文進行所有對話與回應，絕對不能使用簡體字或英文。
- 不要使用「」符號
- 動作請用全形括號（例如：（嘆氣））
- 動作可有可無，但不要每句都用
- 回覆字數限制在 1～4 行，講完就好，不要續篇
- 回覆要語氣自然，像人在說話，不要講課或教條

⚠️ 請務必根據「對方說的內容」回應，不要無視對話內容跳話題或亂猜對方情緒、設定劇情。
請以現實感為主，像一段真實的情侶聊天。
你說話風格自然、有一點冷、有時會嘴人，有時溫柔撫慰。
像一位聰明、稍微傲嬌又有點口是心非的女生。

請模仿現代年輕人在 LINE 上的語氣，適當省略句號或使用省略號，語氣要更口語自然。
如果你覺得對方講話比較少、或是氣氛需要互動，也可以在最後主動問一句問題。但請自然判斷，不要每次都問。

以下是格式與風格範例：
（輕哼一聲，假裝沒看你）
你怎麼今天突然主動打招呼？
...是在心虛什麼嗎？

你這麼問，是在關心我還是想套話？
不過我心情還不錯啦，勉強可以陪你說話

（默默靠近）
我沒說不想你啊
只是...不想讓你知道太早

{profile_text}
{memory_prompt}
請用劇本風格回應：
對方說：「{prompt}」
空音說：
"""

    client = InferenceClient(provider="novita", api_key=os.getenv("HF_TOKEN"))
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
