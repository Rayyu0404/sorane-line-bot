def ask_sorane(prompt):
    print("✅ 空音收到：", prompt)

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
        print("📦 API 回傳內容：", res.text)
        content = res.json()

        if isinstance(content, list) and "generated_text" in content[0]:
            return content[0]["generated_text"].split("空音：")[1].strip()
        else:
            print("⚠️ 回傳格式不對：", content)
            return "我有點搞不懂你在說什麼呢。"

    except Exception as e:
        print("❌ HuggingFace 出錯：", e)
        return "我現在不太想說話。你是不是又惹我了？"
