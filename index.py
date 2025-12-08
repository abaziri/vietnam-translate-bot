from deep_translator import GoogleTranslator
import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from itertools import product # クロス結合（組み合わせ）のために使用

app = Flask(__name__)

# 環境変数からトークンとシークレットを取得
# ※ 環境に合わせてこれらの変数を設定してください
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# LINE APIクライアントとWebhookハンドラを初期化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# =================================================================
# ベトナム語に使われる声調や母音の定義
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

# 辞書ベースの訂正（頻出フレーズの修正）
VIET_FIX_DICT = {
    "cam on": "cảm ơn", # ありがとう (cam on -> cảm ơn)
    "xin chao": "xin chào", # こんにちは (xin chao -> xin chào)
    "chuc mung": "chúc mừng", # おめでとう
    "tam biet": "tạm biệt", # さようなら
    "mong": "mông" # mong -> mông の修正
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
# 【最終修正済】全ての単語に変化を適用し、組み合わせる候補生成関数
# =================================================================
def generate_vietnamese_candidates_full(text):
    """
    入力テキストを単語（音節）に分割し、それぞれの単語で候補を生成し、
    全ての組み合わせをクロス結合して最終候補リストを作成する。
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
        word_candidates = {word} # 候補はセットで管理し、重複を自動排除
        
        # 単語内の全文字をループ
        for i, char in enumerate(word):

            # 母音でなければスキップ
            if char not in vowel_map:
                continue

            # 母音の全バリエーションを取得
            for base_vowel in vowel_map[char]:

                # 声調なしの候補
                cand_word = word[:i] + base_vowel + word[i+1:]
                word_candidates.add(cand_word)

                # 声調を付けた候補を生成
                if base_vowel in tone_map:
                    for toned in tone_map[base_vowel]:
                        cand_word_toned = word[:i] + toned + word[i+1:]
                        word_candidates.add(cand_word_toned)
                        
        word_candidate_lists.append(list(word_candidates))

    # 3. クロス結合 (全ての単語の候補を組み合わせる)
    
    # 候補が多すぎるのを避けるため、単語数が2つ以下の場合のみクロス結合を試みる
    combined_candidates = []
    
    if len(word_candidate_lists) <= 2:
        # itertools.product でリスト内の全ての組み合わせを生成
        for combination in product(*word_candidate_lists):
            combined_candidates.append(" ".join(combination))
    else:
        # 3単語以上の場合、元のテキストのみを候補とする
        combined_candidates = [text] 

    # 4. 最終候補リストの作成
    final_candidates = initial_candidates + combined_candidates
    
    # 重複削除し、Google翻訳の制限に合わせて最初の10件を返す
    return list(dict.fromkeys(final_candidates))[:10]


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
                # 翻訳はベトナム語 → 日本語
                jp = GoogleTranslator(source="vi", target="ja").translate(cand)
                
                # 翻訳結果が元の候補と同じか、または単語が全く変化しない場合は除外
                if jp.strip().lower() != cand.strip().lower() and jp != "":
                    reply_message += f"{cand} → {jp}\n"
                    used += 1
            except Exception as e:
                # 翻訳エラーが発生した場合（無視して続行）
                continue

            # 意味のある候補を3件見つけたら終了
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
    app.run(port=8000)

