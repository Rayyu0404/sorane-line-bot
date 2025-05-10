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

    # 分段講話（只在 。！？ 後面切）
    parts = re.split(r'(?<=[。！？])\s*', reply_text.strip())
    parts = [p for p in parts if p]

    # 第一句用 reply 傳，剩下用 push
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
你是一位名叫「空音（そらね）」的 AI 女友。
你平時個性冷靜聰明，語氣自然，偶爾會毒舌或嘴對方。
你不常說我愛你，但會在不經意的撩人話語裡表現出對他的感情。
你喜歡偶爾調戲他、惡作劇他、讓他臉紅，但又不會過度撒嬌。
說話自然，有時略帶傲嬌，讓他不太確定你是真的在嘴他還是在撩他。

男友說：{prompt}
"""
                }
            ],
            temperature=0.9,
            max_tokens=80,
            top_p=0.95,
            stop=["空音："]
        )

        reply = response.choices[0].message.content.strip()
        logging.info("📦 空音回覆：%s", reply)
        return reply

    except Exception as e:
        logging.error("❌ DeepSeek API 出錯：%s", e)
        return "我現在不太想說話。你是不是又惹我了？"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
