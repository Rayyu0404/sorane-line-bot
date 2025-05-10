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
    user_text = event.message.text
    reply_text = ask_sorane(user_text)

    parts = split_reply(reply_text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=parts[0])
    )

    for i, part in enumerate(parts[1:]):
        threading.Timer(1.5 * (i + 1), lambda msg=part: line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=msg)
        )).start()

def ask_sorane(prompt):
    logging.info("✅ 空音收到：%s", prompt)

    client = InferenceClient(
        provider="novita",
        api_key=os.getenv("HF_TOKEN")
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3-0324",
            messages=[
                {
                    "role": "user",
                    "content": f"""
請用自然語氣回話，不要使用「」符號，也不要太正式。
你說話方式像真人女友，有情緒、有小脾氣，有時冷靜，有時嘴人。
你可以在適當時候加上一些動作（用全形括號表示），但不是每次都需要。

請模仿這種劇本式風格：
（輕哼一聲）  
你突然這麼黏人...怎麼回事？
...不會是想我了吧？
哼，那就勉強陪你一下。

請用這種語氣和節奏回答男友說的話，不要太長。
"""
                }
            ],
            temperature=0.9,
            max_tokens=100,
            top_p=0.95
        )

        reply = response.choices[0].message.content.strip()
        logging.info("📦 空音回覆：%s", reply)
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
            result.append(line)  # 動作獨立一行
        else:
            # 正常語句依 。！？ 做分句
            result += [s.strip() for s in re.split(r'(?<=[。！？])\s*', line) if s.strip()]
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
