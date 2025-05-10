from flask import Flask, request, abort, copy_current_request_context
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import os
import threading
import logging

# 初始化 Flask 與 Log
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 初始化 LINE Bot SDK
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# LINE webhook 接收點
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

# 處理收到的訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    reply_text = ask_sorane(user_text)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# 空音 AI 回覆函式
def ask_sorane(prompt):
    logging.info("✅ 空音收到：%s", prompt)

    headers = {
        "Authorization": f"Bearer {os.getenv('HF_TOKEN')}",
        "Content-Type": "application/json"
    }

    data = {
        "inputs": f"""
你是一位名叫「空音（そらね）」的 AI 女友。
你平時個性冷靜聰明，語氣自然，偶爾會毒舌或嘴對方。
你不常說我愛你，但會在不經意的撩人話語裡表現出對他的感情。
你喜歡偶爾調戲他、惡作劇他、讓他臉紅，但又不會過度撒嬌。
說話自然，有時略帶傲嬌，讓他不太確定你是真的在嘴他還是在撩他。
不要使用過多顏文字或表情符號。

男友說：{prompt}
空音：""",
        "parameters": {
            "max_new_tokens": 100,
            "temperature": 0.8
        }
    }

    try:
        res = requests.post(
            "https://api-inference.huggingface.co/models/deepseek-ai/deepseek-llm-7b-chat",
            headers=headers,
            json=data
        )
        logging.info("📦 API 回傳內容：%s", res.text)
        content = res.json()

        if isinstance(content, list) and "generated_text" in content[0]:
            return content[0]["generated_text"].split("空音：")[1].strip()
        else:
            logging.warning("⚠️ 回傳格式不對：%s", content)
            return "我有點搞不懂你在說什麼呢。"

    except Exception as e:
        logging.error("❌ HuggingFace 出錯：%s", e)
        return "我現在不太想說話。你是不是又惹我了？"

# 正式啟動 Flask 應用
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
