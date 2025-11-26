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

    # =====  言語判定（deep-translator は未対応のため簡易判定） =====
    # ベトナム語っぽい文字（dấu）を含むかどうかで判定
    vietnamese_chars = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"

    def is_vietnamese(text):
        return any(c in vietnamese_chars for c in text.lower())

    # ===== 翻訳処理 =====
    if is_vietnamese(user_text):
        translated = GoogleTranslator(source="vi", target="ja").translate(user_text)
        reply = f"[VI → JP]\n{translated}"
    else:
        translated = GoogleTranslator(source="ja", target="vi").translate(user_text)
        reply = f"[JP → VI]\n{translated}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()


