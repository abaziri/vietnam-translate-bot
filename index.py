import os
import json

# 環境変数にサービスアカウントJSONをまるごと入れた場合の処理
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if creds_json:
    key_path = "/tmp/gcst-key.json"
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(creds_json)
    # GCPライブラリはこの環境変数を参照して認証します
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

from deep_translator import GoogleTranslator
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
# AudioMessageとその他のモデルをインポート
from linebot.models import MessageEvent, TextMessage, TextSendMessage, AudioMessage 
from itertools import product 
from google.cloud import speech # GCSTクライアント
from google.cloud.speech import RecognitionConfig, RecognitionAudio

app = Flask(__name__)

# 環境変数からトークンとシークレットを取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# LINE APIクライアントとWebhookハンドラを初期化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# =================================================================
# 1. GCSTクライアントと設定の初期化 (音声認識用)
# =================================================================
# GCSTクライアントの初期化
try:
    gcst_client = speech.SpeechClient()
except Exception as e:
    print(f"GCST Client Initialization Error. Check GOOGLE_APPLICATION_CREDENTIALS: {e}")
    gcst_client = None

# ベトナム語の認識設定 (vi-VNで方言に対応)
VIETNAMESE_STT_CONFIG = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS, 
    sample_rate_hertz=16000,
    language_code="vi-VN"    # ベトナム語（地域指定）
)

# =================================================================
# 2. ベトナム語 声調/母音の定義と辞書
# =================================================================
vietnamese_accent_chars = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"

vowel_map = {
    "a": ["a", "ă", "â"], "o": ["o", "ô", "ơ"], "u": ["u", "ư"],
    "e": ["e", "ê"], "i": ["i"], "y": ["y"]
}

tone_map = {
    "a": ["á", "à", "ả", "ã", "ạ"], "ă": ["ắ", "ằ", "ẳ", "ẵ", "ặ"],
    "â": ["ấ", "ầ", "ẩ", "ẫ", "ậ"], "e": ["é", "è", "ẻ", "ẽ", "ẹ"],
    "ê": ["ế", "ề", "ể", "ễ", "ệ"], "i": ["í", "ì", "ỉ", "ĩ", "ị"],
    "o": ["ó", "ò", "ỏ", "õ", "ọ"], "ô": ["ố", "ồ", "ổ", "ỗ", "ộ"],
    "ơ": ["ớ", "ờ", "ở", "ỡ", "ợ"], "u": ["ú", "ù", "ủ", "ũ", "ụ"],
    "ư": ["ứ", "ừ", "ử", "ữ", "ự"], "y": ["ý", "ỳ", "ỷ", "ỹ", "ỵ"]
}

# 辞書ベースの訂正（頻出フレーズの修正）
VIET_FIX_DICT = {
    "cam on": "cảm ơn", "xin chao": "xin chào", "chuc mung": "chúc mừng",
    "tam biet": "tạm biệt", "mong": "mông"
}

# =================================================================
# 3. 判定関数と候補生成関数
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

def generate_vietnamese_candidates_full(text):
    """
    全ての単語に変化を適用し、組み合わせる候補生成関数。
    """
    text = text.lower().strip()
    words = text.split()
    
    initial_candidates = []
    
    # 1. 辞書による自動修正候補 (最優先)
    if text in VIET_FIX_DICT:
        initial_candidates.append(VIET_FIX_DICT[text])
        
    if not words:
        return initial_candidates

    # 2. 各単語の候補リストを生成
    word_candidate_lists = []
    for word in words:
        word_candidates = {word} 
        for i, char in enumerate(word):
            if char not in vowel_map:
                continue
            for base_vowel in vowel_map[char]:
                cand_word = word[:i] + base_vowel + word[i+1:]
                word_candidates.add(cand_word)
                if base_vowel in tone_map:
                    for toned in tone_map[base_vowel]:
                        cand_word_toned = word[:i] + toned + word[i+1:]
                        word_candidates.add(cand_word_toned)
        word_candidate_lists.append(list(word_candidates))

    # 3. クロス結合 (全ての単語の候補を組み合わせる)
    combined_candidates = []
    
    # 候補が多すぎるのを避けるため、単語数が2つ以下の場合のみクロス結合
    if len(word_candidate_lists) <= 2:
        for combination in product(*word_candidate_lists):
            combined_candidates.append(" ".join(combination))
    else:
        # 3単語以上の場合、元のテキストのみを候補とする
        combined_candidates = [text] 

    # 4. 最終候補リストの作成
    final_candidates = initial_candidates + combined_candidates
    
    # 重複削除し、最初の10件を返す
    return list(dict.fromkeys(final_candidates))[:10]


# =================================================================
# 4. LINE Webhookとハンドラ (音声・テキスト処理)
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

# 【追加】音声メッセージハンドラ
@handler.add(MessageEvent, message=AudioMessage)
def handle_audio_message(event):
    if not gcst_client:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="エラー：音声認識サービスが利用できません。")
        )
        return
        
    message_content = line_bot_api.get_message_content(event.message.id)
    audio_bytes = message_content.content
    transcribed_text = ""
    
    # GCSTに送信してテキスト化 (ベトナム語として試行)
    try:
        audio = RecognitionAudio(content=audio_bytes)
        response_vi = gcst_client.recognize(config=VIETNAMESE_STT_CONFIG, audio=audio)

        if response_vi.results:
            transcribed_text = response_vi.results[0].alternatives[0].transcript
        
    except Exception as e:
        print(f"GCST Error: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="音声認識中にエラーが発生しました。設定を確認してください。")
        )
        return

    if not transcribed_text:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="認識結果が空でした。もう一度お話しください。")
        )
        return

    # 認識されたテキストを使って翻訳を実行
    if is_vietnamese(transcribed_text) or is_vietnamese_no_tone(transcribed_text):
        translated = GoogleTranslator(source="vi", target="ja").translate(transcribed_text)
        reply_text = f"🇻🇳（認識結果：{transcribed_text}）\n\n🇯🇵翻訳：{translated}"
    else:
        translated = GoogleTranslator(source="ja", target="vi").translate(transcribed_text)
        reply_text = f"🇯🇵（認識結果：{transcribed_text}）\n\n🇻🇳翻訳：{translated}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


# 【既存】テキストメッセージハンドラ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    user_text = event.message.text

    # ① 声調なしベトナム語 → 候補生成
    if is_vietnamese_no_tone(user_text):

        candidates = generate_vietnamese_candidates_full(user_text)

        reply_message = "候補（意味のあるもののみ）：\n\n"
        used = 0

        for cand in candidates:
            try:
                jp = GoogleTranslator(source="vi", target="ja").translate(cand)
                
                if jp.strip().lower() != cand.strip().lower() and jp != "":
                    reply_message += f"{cand} → {jp}\n"
                    used += 1
            except Exception as e:
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

    # ② 声調付きベトナム語 → 日本語翻訳
    if is_vietnamese(user_text):
        translated = GoogleTranslator(source="vi", target="ja").translate(user_text)
        reply = translated

    # ③ 日本語 → ベトナム語翻訳
    else:
        translated = GoogleTranslator(source="ja", target="vi").translate(user_text)
        reply = translated

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run(port=8000)


