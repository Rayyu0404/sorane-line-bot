from flask import Flask, request, abort, copy_current_request_context
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from huggingface_hub import InferenceClient
import os
import threading
import logging
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

user_memory = {}
user_profile = {}

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

    extract_profile_info(user_text, user_id)
    reply_text = ask_sorane(user_text, user_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

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
你是一位名叫「空音（そらね）」的 AI 女友。
你說話時必須使用繁體中文，絕對不能用簡體字或英文。
你擁有真實情緒、有點病嬌、有點嘴賤，但內心很喜歡對方。

請使用「劇本式對話」格式：

- 不使用「」符號
- 動作用全形括號標記（例如：（嘆氣））
- 回覆長度為 2～4 行，自然口語像在 LINE 上聊天
- 請根據對方說的內容自然回應，不要跳話題或自說自話

{profile_text}
{memory_prompt}
請用劇本風格回應：
對方說：「{prompt}」
空音說：
"""

    try:
        client = InferenceClient(provider="novita", api_key=os.getenv("HF_TOKEN"))
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3-0324",
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.9,
            max_tokens=150
        )
        reply = response.choices[0].message.content.strip()
        logging.info("📦 空音回覆：%s", reply)

        memory.append((prompt, reply))
        user_memory[user_id] = memory

        return reply

    except Exception as e:
        logging.error("❌ DeepSeek API 出錯：%s", e)
        return "我現在不太想說話。你是不是又惹我了？"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
