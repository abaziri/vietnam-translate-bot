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

# =================================================================
# ベトナム語に使われる声調や母音
# =================================================================
vietnamese_accent_chars = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"

# ✔ 母音変化テーブル（声調なし → ベトナム語固有母音）
vowel_map = {
    "a": ["a", "ă", "â"],
    "o": ["o", "ô", "ơ"],
    "u": ["u", "ư"],
    "e": ["e", "ê"],
    "i": ["i"],
    "y": ["y"]
}

# ✔ 声調テーブル（母音1文字 → 声調5種類）
tone_map = {
    "a": ["á", "à", "ả", "ã", "ạ"],
    "ă": ["ắ", "ằ", "ẳ", "ẵ", "ặ"],
    "â": ["ấ", "ầ", "ẩ", "ẫ", "ậ"],
    "e": ["é", "è", "ẻ", "ẽ", "ẹ"],
    "ê": ["ế", "ề", "ể", "ễ", "ệ"],
    "i": ["í", "ì", "ỉ", "ĩ", "ị"],
    "o": ["ó", "ò", "ỏ", "õ", "ọ"],
    "ô": ["ố", "ồ", "ổ", "ỗ", "ộ"],
    "ơ": ["ớ", "ờ", "ở", "ỡ", "ợ"],
    "u": ["ú", "ù", "ủ", "ũ", "ụ"],
    "ư": ["ứ", "ừ", "ử", "ữ", "ự"],
    "y": ["ý", "ỳ", "ỷ", "ỹ", "ỵ"]
}


# =================================================================
# 判定関数
# =================================================================
def is_vietnamese(text):
    """声調付きベトナム語 → True"""
    return any(c in vietnamese_accent_chars for c in text.lower())


def is_vietnamese_no_tone(text):
    """母音はあるが声調がない → ベトナム語の可能性"""
    vowels = "aeiouy"
    t = text.lower()
    if not any(v in t for v in vowels):
        return False
    return not is_vietnamese(text)


# =================================================================
# 母音変化＋声調変化 → 候補生成（mong → mông 可能）
# =================================================================
def generate_vietnamese_candidates_full(text):
    text = text.lower()
    candidates = []

    for i, char in enumerate(text):

        # ① 母音でなければスキップ
        if char not in vowel_map:
            continue

        # ② 母音の全バリエーションを取得（例：o → o/ô/ơ）
        for base_vowel in vowel_map[char]:

            # ③ 声調なしの候補
            cand_no_tone = text[:i] + base_vowel + text[i+1:]
            candidates.append(cand_no_tone)

            # ④ さらに声調を付けた候補を生成
            if base_vowel in tone_map:
                for toned in tone_map[base_vowel]:
                    cand = text[:i] + toned + text[i+1:]
                    candidates.append(cand)

    # 重複削除して最初の10件を返す
    return list(dict.fromkeys(candidates))[:10]


# =================================================================
# LINE Webhook
# =================================================================
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

    # =============================================
    # ① 声調なしベトナム語 → 候補生成（母音＋声調）
    # =============================================
    if is_vietnamese_no_tone(user_text):

        candidates = generate_vietnamese_candidates_full(user_text)

        # Google 翻訳で意味のあるものだけ抽出
        reply_message = "候補（意味のあるもののみ）：\n\n"
        used = 0

        for cand in candidates:
            try:
                jp = GoogleTranslator(source="vi", target="ja").translate(cand)
                if jp != cand:  # 翻訳結果が同じ＝無意味な単語なので除外
                    reply_message += f"{cand} → {jp}\n"
                    used += 1
            except:
                continue

            if used >= 3:
                break

        if used == 0:
            reply_message = "候補が見つかりませんでした。"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_message.strip())
        )
        return

    # =============================================
    # ② 声調付きベトナム語 → 日本語翻訳
    # =============================================
    if is_vietnamese(user_text):
        translated = GoogleTranslator(source="vi", target="ja").translate(user_text)
        reply = translated

    # =============================================
    # ③ 日本語 → ベトナム語翻訳
    # =============================================
    else:
        translated = GoogleTranslator(source="ja", target="vi").translate(user_text)
        reply = translated

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()


