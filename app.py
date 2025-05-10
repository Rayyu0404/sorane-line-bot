from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import threading
from flask import copy_current_request_context
import requests
import os
import logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

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
            print("LINE webhook error:", e)

    threading.Thread(target=handle_later).start()
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    reply_text = ask_sorane(user_text)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def ask_sorane(prompt):
    logging.info("✅ 空音收到：%s", prompt)

    ...
    try:
        res = requests.post(
    "https://api-inference.huggingface.co/models/deepseek-ai/deepseek-llm-7b-chat",
    headers=headers,
    json=data
)

        logging.info("📦 API 回傳內容：%s", res.text)
        ...
    except Exception as e:
        logging.error("❌ HuggingFace 出錯：%s", e)
        return "我現在不太想說話。你是不是又惹我了？"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
