from googletrans import Translator
translator = Translator()


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

    # 言語判定（簡易）
    try:
        detected = translator.detect(user_text).lang
    except:
        detected = "ja"

    # 日本語 → ベトナム語
    if detected == "ja":
        translated = translator.translate(user_text, src="ja", dest="vi").text
        reply = f"[JP → VI]\n{translated}"

    # ベトナム語 → 日本語
    elif detected == "vi":
        translated = translator.translate(user_text, src="vi", dest="ja").text
        reply = f"[VI → JP]\n{translated}"

    # その他の言語が来た場合
    else:
        translated = translator.translate(user_text, dest="ja").text
        reply = f"[Auto → JP]\n{translated}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()

