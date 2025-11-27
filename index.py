from deep_translator import GoogleTranslator
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ベトナム語に使われる声調文字（dấu）
vietnamese_accent_chars = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"

# 声調が付いていない母音 → 対応する声調付き候補
tone_map = {
    "a": ["á", "à", "ả", "ã", "ạ"],
    "e": ["é", "è", "ẻ", "ẽ", "ẹ"],
    "i": ["í", "ì", "ỉ", "ĩ", "ị"],
    "o": ["ó", "ò", "ỏ", "õ", "ọ"],
    "u": ["ú", "ù", "ủ", "ũ", "ụ"],
    "y": ["ý", "ỳ", "ỷ", "ỹ", "ỵ"]
}

def is_vietnamese(text):
    """すでに声調が含まれている場合 True"""
    return any(c in vietnamese_accent_chars for c in text.lower())

def is_vietnamese_no_tone(text):
    """ベトナム語の母音はあるが声調がない場合 True"""
    vowels = "aeiouy"
    text_lower = text.lower()

    if not any(v in text_lower for v in vowels):
        return False  # 母音がない＝ベトナム語ではない

    return not is_vietnamese(text)

def generate_vietnamese_candidates(text):
    """声調なしの単語から候補３つを作る"""
    candidates = []

    for i, c in enumerate(text.lower()):
        if c in tone_map:
            for tone in tone_map[c]:
                cand = text[:i] + tone + text[i+1:]
                candidates.append(cand)

    return candidates[:3]  # 最初の3つだけ使う

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Error:", e)
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text

    # ① 声調なしベトナム語を判定
    if is_vietnamese_no_tone(user_text):
        candidates = generate_vietnamese_candidates(user_text)

        reply_message = "予測される候補３つ：\n\n"

        for cand in candidates:
            jp = GoogleTranslator(source="vi", target="ja").translate(cand)
            reply_message += f"{cand} → {jp}\n"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_message.strip())
        )
        return

    # ② すでに声調付き → 日本語へ翻訳
    if is_vietnamese(user_text):
        translated = GoogleTranslator(source="vi", target="ja").translate(user_text)
        reply = translated

    # ③ 日本語 → ベトナム語へ翻訳
    else:
        translated = GoogleTranslator(source="ja", target="vi").translate(user_text)
        reply = translated

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run()



