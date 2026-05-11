import streamlit as st
from PIL import Image
import re
import pandas as pd # データを表形式で扱うためのライブラリ
from datetime import datetime # 日付を扱うためのライブラリ
import os
import altair as alt
from google.cloud import vision
from google.api_core.client_options import ClientOptions
import hashlib # パスワード暗号化のための標準ライブラリ
from streamlit_calendar import calendar

USER_DB_FILE = "users.csv" # ユーザー情報を保存するファイル

# --- カテゴリの定義 ---
CATEGORIES = ["未分類", "食費", "日用品", "交通費", "エンタメ", "洋服", "コンビニ", "その他"]

# --- パスワード暗号化関数 ---
def hash_password(password):
    # パスワードをSHA-256という方式で解読不能な文字列に変換する
    return hashlib.sha256(password.encode()).hexdigest()

# --- ユーザー情報の読み込み・登録関数 ---
def load_users():
    if os.path.exists(USER_DB_FILE):
        return pd.read_csv(USER_DB_FILE)
    else:
        return pd.DataFrame(columns=["username", "password_hash"])

def register_user(username, password):
    df = load_users()
    if username in df["username"].values:
        return False # 既に存在するユーザー名の場合は失敗
    
    new_user = pd.DataFrame({
        "username": [username],
        "password_hash": [hash_password(password)] # 暗号化して保存！
    })
    df = pd.concat([df, new_user], ignore_index=True)
    df.to_csv(USER_DB_FILE, index=False)
    return True

def authenticate_user(username, password):
    df = load_users()
    # ユーザー名が一致し、かつ「入力されたパスワードを暗号化したもの」が保存データと一致するか確認
    match = df[(df["username"] == username) & (df["password_hash"] == hash_password(password))]
    return not match.empty

# --- データの読み込み・保存（カテゴリ対応版） ---
def get_db_filename(user_name):
    # ユーザー名を使って専用のファイル名を生成する
    return f"{user_name}_expense_history.csv"

def load_data(user_name):
    target_file = get_db_filename(user_name)
    if os.path.exists(target_file):
        return pd.read_csv(target_file)
    else:
        # ファイルがない（初めてのユーザー）場合は空の表を作る # 【追加】category 列を追加
        return pd.DataFrame(columns=["date", "item", "amount", "category"])

# --- データの読み込み・保存（引数に transaction_date を追加） ---
def save_data(user_name, item_name, amount, category, transaction_date=None):
    target_file = get_db_filename(user_name)
    df = load_data(user_name)
    clean_amount = int(amount)
    
    # もし日付が指定されていなければ「今日」にする（手動入力などのバックアップ用）
    if not transaction_date:
        transaction_date = datetime.now().strftime("%Y-%m-%d")
        
    new_data = pd.DataFrame({
        "date": [transaction_date], 
        "item": [item_name],
        "amount": [clean_amount],
        "category": [category]
    })
    
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(target_file, index=False)

# --- 店舗の自動分類辞書機能 ---
def get_dict_filename(user_name):
    return f"{user_name}_store_dict.csv"

def load_store_dict(user_name):
    # 登録済みの店舗とカテゴリを辞書形式で読み込む
    dict_file = get_dict_filename(user_name)
    if os.path.exists(dict_file):
        return pd.read_csv(dict_file).set_index("store")["category"].to_dict()
    return {}

def save_store_dict(user_name, store, category):
    # 未知の店舗を新しく辞書に学習させる
    dict_file = get_dict_filename(user_name)
    new_data = pd.DataFrame({"store": [store], "category": [category]})
    if os.path.exists(dict_file):
        df = pd.read_csv(dict_file)
        # 古いデータがあれば消して新しいもので上書き
        df = df[df["store"] != store]
        df = pd.concat([df, new_data], ignore_index=True)
    else:
        df = new_data
    df.to_csv(dict_file, index=False)

def ocr_with_vision_api(uploaded_file):
    # APIキーを設定（※本来は直接書かず、隠すのがベストですが、まずはテスト用）
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    
    # ファイルの読み取り位置を先頭に戻す（以前学んだ必須テクニック）
    uploaded_file.seek(0)
    content = uploaded_file.read()
    
    # APIキーを使ってGoogleのクライアントを準備
    client_options = ClientOptions(api_key=API_KEY)
    client = vision.ImageAnnotatorClient(client_options=client_options)
    
    # 画像をセットしてテキスト検出を実行
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    # エラーチェック（万が一Google側でエラーが起きた場合）
    if response.error.message:
        st.error(f"APIエラー: {response.error.message}")
        return ""
        
    # 読み取り結果があれば、全文（0番目のデータ）を返す
    if texts:
        return texts[0].description
    else:
        return ""

# --- 画面構成 ---
st.set_page_config(page_title="AI家計簿", layout="wide")

if "pending_transactions" not in st.session_state:
    st.session_state["pending_transactions"] = []

# --- セッション（記憶）の初期化 ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["current_user"] = ""

# ==========================================
# 画面ルーティング（表示の切り替え）
# ==========================================
if not st.session_state["logged_in"]:
    # --- 🚪 ログイン・新規登録画面 ---
    st.title("🛡️ AI家計簿システム - ログイン")
    
    # タブを使ってログインと新規登録を切り替えられるようにする
    tab_login, tab_register = st.tabs(["ログイン", "新規ユーザー登録"])
    
    with tab_login:
        st.subheader("ログイン")
        # 🌟 ここからフォーム機能を使用する
        with st.form("login_form"):
            login_user = st.text_input("ユーザー名")
            login_pass = st.text_input("パスワード", type="password")
            
            # 通常の st.button ではなく、フォーム専用の送信ボタンを使う
            submit_login = st.form_submit_button("ログインする")
            
            if submit_login:
                if authenticate_user(login_user, login_pass):
                    st.session_state["logged_in"] = True
                    st.session_state["current_user"] = login_user
                    st.success(f"{login_user} さん、ようこそ！")
                    st.rerun() 
                else:
                    st.error("ユーザー名かパスワードが間違っています。")
                
    with tab_register:
        st.subheader("新規ユーザー登録")
        # 🌟 新規登録もフォームでまとめる
        with st.form("register_form"):
            reg_user = st.text_input("希望するユーザー名")
            reg_pass = st.text_input("パスワード", type="password")
            reg_pass_confirm = st.text_input("パスワード（確認用）", type="password")
            
            submit_register = st.form_submit_button("登録してはじめる")
            
            if submit_register:
                if reg_pass != reg_pass_confirm:
                    st.error("パスワードが一致しません。")
                elif not reg_user or not reg_pass:
                    st.error("ユーザー名とパスワードを入力してください。")
                else:
                    if register_user(reg_user, reg_pass):
                        st.success("登録が完了しました！「ログイン」タブからログインしてください。")
                    else:
                        st.error("そのユーザー名は既に使用されています。")

else:
    # ----------------------------------------
    # 🏠 メイン画面（ログイン成功後）
    # ----------------------------------------
    current_user = st.session_state["current_user"]
    st.title(f"🛡️ AI家計簿システム - {current_user} さんのダッシュボード")
    
    if st.sidebar.button("ログアウト"):
        st.session_state["logged_in"] = False
        st.session_state["current_user"] = ""
        st.rerun()

    st.sidebar.divider()
    
    # --- 収支設定 ---
    st.sidebar.header("💰 収支設定")
    monthly_income = st.sidebar.number_input("あなたの月収（円）", value=250000, step=1000)
    target_savings = st.sidebar.number_input("月間の貯金目標（円）", value=50000, step=1000)
    allowable_expense = monthly_income - target_savings

    st.sidebar.divider()

    # 🌟 新機能：ページ切り替えメニュー
    st.sidebar.header("📂 メニュー")
    page = st.sidebar.radio("表示する画面を選んでください", ["📝 記録・読み取り", "📊 分析・カレンダー"])


    # --- メイン：OCRセクション ---

    # ==========================================
    # ページ1：記録・読み取り画面
    # ==========================================

    if page == "📝 記録・読み取り":
        st.subheader("📸 レシート・履歴の読み取り")
        mode = st.radio("読み取り対象を選択", ["レシート（合計1つ）", "PayPay履歴（リスト合計）"])
    
        # 【レシートモード専用UI】
        receipt_category = None
        if mode == "レシート（合計1つ）":
            receipt_category = st.selectbox("このレシートのカテゴリーを選択", [c for c in CATEGORIES if c != "未分類"])
        
        # --- 🌟新機能：画像入力方法の切り替えUI ---
        input_method = st.radio("画像の入力方法", ["📁 フォルダからアップロード", "📷 カメラで直接撮影"], horizontal=True)
    
        uploaded_file = None # 初期化
    
        # 選択された方法に応じてUIを切り替える
        if input_method == "📁 フォルダからアップロード":
            uploaded_file = st.file_uploader("画像をアップロード", type=['png', 'jpg', 'jpeg'])
        else:
            # Streamlitの魔法の関数。ブラウザ経由でスマホやPCのカメラを起動します
            uploaded_file = st.camera_input("カメラを起動して撮影")

        if uploaded_file:
            # プレビュー表示（※カメラ撮影の場合はcamera_input自体がプレビューを出すため、
            # 二重表示を避けるための小さな工夫を入れます）
            if input_method == "📁 フォルダからアップロード":
                image = Image.open(uploaded_file)
                st.image(image, use_container_width=True)
        
            if st.button("OCR実行"):
                with st.spinner('Google Cloud AIが解析中...'):
                    raw_text = ocr_with_vision_api(uploaded_file)
            
                if raw_text:
                    lines = raw_text.split('\n')
                
                    # --- 🌟 レシートモード ---
                    if mode == "レシート（合計1つ）":
                        purchases = []
                        total_amount = 0
                        temp_item_name = ""
                    
                        # レシート全体から「〇〇〇〇年〇月〇日」を探し出す
                        receipt_date = None
                        date_match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', raw_text)
                        if date_match:
                            # 4月を「04」のように2桁に揃えて YYYY-MM-DD 形式を作る（zfillの魔法）
                            yyyy = date_match.group(1)
                            mm = date_match.group(2).zfill(2)
                            dd = date_match.group(3).zfill(2)
                            receipt_date = f"{yyyy}-{mm}-{dd}"
                    
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue # 空白行は無視（ただしtemp_item_nameは保持する）
                            
                            # ① 合計金額の抽出（「計」の誤読「言十」にも対応）
                            # クレジット計や小計は無視し、最大の金額を合計とするため、ここでは候補を全て探します
                            if re.search(r'(合\s*計|合\s*言十)', line):
                                nums = re.findall(r'[0-9,]+', line)
                                if nums:
                                    total_amount = int(nums[-1].replace(',', ''))
                                continue
                            
                            # ② ノイズ行のスキップ（「額」「税」が含まれる行は無条件で無視）
                            if re.search(r'(額|税|伝票|テーブル|点数|お釣|預り|クレジット|No)', line):
                                temp_item_name = "" # ノイズが来たら一時記憶もリセット
                                continue
                            
                            # ③ 商品と金額の抽出
                            match = re.search(r'^(.*?)[¥￥\\]\s*([0-9,]+)', line)
                        
                            if match:
                                left_part = match.group(1).strip()
                                price_str = match.group(2).replace(',', '')
                            
                                # 一時記憶があり、左側が@等で始まるか空白なら結合
                                if temp_item_name and (not left_part or re.search(r'^[@＠\d]', left_part)):
                                    item_name = f"{temp_item_name} {left_part}".strip()
                                else:
                                    item_name = left_part
                            
                                # 商品名が空白でない場合のみリストに追加
                                if item_name:
                                    purchases.append({"item": item_name, "amount": int(price_str)})
                            
                                temp_item_name = "" # 処理完了したのでリセット
                            
                            else:
                                # 「¥」がない行は次の商品名かもしれないのでキープ
                                temp_item_name = line
                    
                        # --- 結果の表示とスマート保存 ---
                        if purchases or total_amount > 0:
                            st.success("以下の内容を抽出しました！")
                        
                            if purchases:
                                st.table(purchases)
                        
                            # 合計金額が読み取れなかった場合のバックアップ（商品の合算値を使う）
                            if total_amount == 0 and purchases:
                                total_amount = sum(p["amount"] for p in purchases)
                                st.info("※合計金額の表記が見つからなかったため、明細の合算値を採用しました。")
                            
                            if total_amount > 0:
                                st.metric("今回の支出額（合計）", f"{total_amount:,} 円")
                            
                                # 【スマート保存】明細を1つの文字列（メモ）に連結する
                                # 例: "七種海鮮丼, サーモンいくら丼, まぐろ @352x 2"
                                details_text = " / ".join([p["item"] for p in purchases])
                            
                                # データベースには「1つの取引」として保存（金額は合計のみ）
                                save_data(current_user, f"レシート: {details_text}", total_amount, receipt_category, receipt_date)
                                st.success(f"✅ {receipt_category} として記録しました！")
                                st.info("✅ 明細をメモとして記録し、合計金額のみを支出として家計簿に追加しました。")

                        else:
                            st.warning("商品と金額のペアが見つかりませんでした。")

                    # --- PayPay履歴モード（AIの癖を見抜いたリスト合体ロジック） ---
                    else:
                        transactions = []
                        store_names = [] # 店舗名だけを貯めるリスト
                        amounts = []     # 金額だけを貯めるリスト
                        dates = []    # 日付を貯めるリスト
                        current_store_parts = [] # 店舗名の「パーツ」を一時的に貯める箱
                    
                        # 1行ずつ上から解析する
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            
                            # ① 金額行の抽出（〇〇円）
                            # 数字と「円」だけで構成されている行を見つけたら金額リストに入れる
                            if re.search(r'^[\d,]+\s*円$', line):
                                clean_num = re.sub(r'[^\d]', '', line)
                                if clean_num:
                                    amounts.append(int(clean_num))
                                continue
                            
                            # ② 日付行の検出（ここが1つの取引の「店舗名の終わり」の合図）
                            date_match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', line)
                            if date_match:
                                yyyy = date_match.group(1)
                                mm = date_match.group(2).zfill(2)
                                dd = date_match.group(3).zfill(2)
                                dates.append(f"{yyyy}-{mm}-{dd}") # リストに追加
                                # 日付が来たら、それまでに貯めていたテキストを繋げて店舗名にする
                                if current_store_parts:
                                    # 「G」などのアイコンの誤読（英語1文字）を除外して結合
                                    valid_parts = [p for p in current_store_parts if len(p) > 1 or not p.isascii()]
                                    if valid_parts:
                                        store_names.append(" ".join(valid_parts))
                                    else:
                                        store_names.append("不明な店舗")
                                else:
                                    store_names.append("不明な店舗")
                                
                                # 次の取引に向けて一時箱を空にする
                                current_store_parts = []
                                continue
                            
                            # ③ ノイズのリセット（「残高」「支払い完了」などは店舗名に含めない）
                            if line in ["残高", "支払い完了", "詳細"]:
                                current_store_parts = []
                                continue
                            
                            # ④ 上記のどれでもない場合、それは「店舗名」の一部として一時箱に入れる
                            current_store_parts.append(line)
                    
                        # --- 最後に店舗リストと金額リストを合体させる ---
                        # 件数がピッタリ一致しているかチェックする（安全装置）
                        min_len = min(len(store_names), len(amounts))
                    
                        if len(store_names) != len(amounts):
                            st.warning(f"⚠️ 店舗名({len(store_names)}件)と金額({len(amounts)}件)の数が一致しませんでした。推測で結合します。")
                    
                        for i in range(min_len):
                            transactions.append({"date": dates[i], "item": store_names[i], "amount": amounts[i]})

                        # 結果の表示と保存
                        if transactions:
                            store_dict = load_store_dict(current_user)
                            pending = []
                            for t in transactions:
                                store_name = t["item"]
                                # 辞書にあればそのカテゴリ、なければ「未分類」にする
                                t["category"] = store_dict.get(store_name, "未分類")
                                pending.append(t)
                            
                            # 解析結果を一旦セッションに保存（この後、画面下部で処理させる）
                            st.session_state["pending_transactions"] = pending
                            st.success("読み取り完了！分類を確認してください。")
                        else:
                            st.warning("取引が見つかりませんでした。")

        # --- 未分類店舗の振り分けUI（PayPayモードでOCR実行後に表示される） ---
        if st.session_state["pending_transactions"]:
            st.divider()
            st.subheader("🏷️ カテゴリの確認と振り分け")
        
            updated_transactions = []
            all_categorized = True # 全て分類されたかチェックするフラグ
        
            for i, t in enumerate(st.session_state["pending_transactions"]):
                store = t["item"]
                amount = t["amount"]
                current_cat = t["category"]
                txn_date = t.get("date", "日付不明")
            
                if current_cat == "未分類":
                    st.warning(f"⚠️ [{txn_date}] 「{store}」({amount}円) は未登録です。")
                    # ユーザーにカテゴリを選ばせる
                    new_cat = st.selectbox(f"「{store}」のグループ", CATEGORIES, key=f"cat_{i}")
                    t["category"] = new_cat
                    if new_cat == "未分類":
                        all_categorized = False # まだ未分類が残っている
                else:
                    st.info(f"✅ [{txn_date}] {store} ({amount}円) ➔ {current_cat} (自動分類)")
            
                updated_transactions.append(t)
            
            # 全て分類された場合のみ、保存ボタンが押せるようになる
            if st.button("データベースに保存して学習させる", disabled=not all_categorized):
                for t in updated_transactions:
                    # 家計簿に保存
                    save_data(current_user, t["item"], t["amount"], t["category"], t.get("date"))
                    # 辞書に学習させて、次回から自動分類させる
                    save_store_dict(current_user, t["item"], t["category"])
                
                st.success("すべての記録と学習が完了しました！")
                st.session_state["pending_transactions"] = [] # 一時データを消去
                st.rerun() # 画面をリロードしてグラフを更新

    # ==========================================
    # ページ2：分析・カレンダー画面
    # ==========================================

    elif page == "📊 分析・カレンダー":
        st.subheader("📈 支出履歴と分析")
        df_history = load_data(current_user)
    
        if not df_history.empty:
            # 日付を読みやすく変換
            df_history['date'] = pd.to_datetime(df_history['date'])
            # 今月のデータだけを抽出
            current_month = datetime.now().month
            this_month_df = df_history[df_history['date'].dt.month == current_month]
            this_month_amounts = pd.to_numeric(this_month_df['amount'], errors='coerce').fillna(0)
        
            total_this_month = int(this_month_amounts.sum())
            remaining = allowable_expense - total_this_month
        
            # 状況メーター
            st.metric("今月の総支出", f"{total_this_month:,} 円")
            st.metric("今月の残り予算", f"{remaining:,} 円", delta=f"{remaining} 円")
        
            if remaining < 0:
                st.error("⚠️ 予算オーバーです！貯金目標がピンチです。")
        
            st.write("直近の記録")
            st.dataframe(df_history.tail(5), use_container_width=True)
        else:
            st.info("データがまだありません。レシートを読み取ってください。")

        if not df_history.empty:
            df_history['date'] = pd.to_datetime(df_history['date'])
            current_month = datetime.now().month
            this_month_df = df_history[df_history['date'].dt.month == current_month]
        
            # ...（これまでの予算計算などはそのまま）...
        
            # --- カテゴリ別支出の円グラフ ---
            st.divider()
            st.subheader("📊 今月のカテゴリ別支出")
        
            if not this_month_df.empty:
                # カテゴリごとに金額を合計
                category_summary = this_month_df.groupby('category', as_index=False)['amount'].sum()
            
                # Altairで円グラフ（ドーナツチャート）を作成
                pie_chart = alt.Chart(category_summary).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta(field="amount", type="quantitative"),
                    color=alt.Color(field="category", type="nominal", title="カテゴリ"),
                    tooltip=["category", "amount"]
                ).interactive()
            
                st.altair_chart(pie_chart, use_container_width=True)
            
                # 履歴も表示
                st.write("直近の記録")
                st.dataframe(df_history.tail(5), use_container_width=True)

            st.divider()
            st.subheader("📅 今月の支出カレンダー")

            if not this_month_df.empty:
                # 1. 同じ日に複数回の買い物がある場合、日付ごとに合計金額をまとめる
                daily_summary = this_month_df.groupby(this_month_df['date'].dt.strftime('%Y-%m-%d'), as_index=False)['amount'].sum()

                # 2. カレンダーに表示する「イベント」のデータを作成する
                calendar_events = []
                for _, row in daily_summary.iterrows():
                    calendar_events.append({
                        "title": f"¥ {int(row['amount']):,}", # カレンダーのマスに表示する文字（金額）
                        "start": row['date'],                 # 日付
                        "color": "#FF4B4B",                   # イベントの色（Streamlitのテーマカラーの赤）
                        "display": "block"
                    })

                # 3. カレンダーの見た目や動作の設定（プロフェッショナルなUI設計）
                calendar_options = {
                    "headerToolbar": {
                        "left": "today prev,next",
                        "center": "title",
                        "right": "dayGridMonth"
                    },
                    "initialView": "dayGridMonth",
                    "locale": "ja", # 【重要】カレンダーを日本語化する魔法の設定
                }

                # 4. カレンダーを画面に描画する
                calendar(events=calendar_events, options=calendar_options)

            else:
                st.info("今月の記録はまだありません。")

        # --- 月ごとの集計グラフ (安定表示版) ---
        if not df_history.empty:
            st.divider()
            st.subheader("🗓️ 月別支出推移")

            # 1. データの集計
            # 一度集計してから、date列を「グラフが読みやすい形式」に作り直します
            monthly_summary = df_history.resample('ME', on='date').sum().reset_index()
    
            # 【ここが重要！】date列を「2026-04-01」のような標準的な日付形式に強制変換
            monthly_summary['date'] = monthly_summary['date'].dt.to_period('M').dt.to_timestamp()

            # 2. 支出の棒グラフ
            bars = alt.Chart(monthly_summary).mark_bar(
                color='#4682b4', # 落ち着いた青色
                size=40          # 棒を少し太くして存在感を出す
            ).encode(
                x=alt.X('date:T', title='月', axis=alt.Axis(format='%Y/%m', labelAngle=0)),
                y=alt.Y('amount:Q', title='支出額 (円)'),
                tooltip=[
                    alt.Tooltip('date:T', title='月', format='%Y/%m'),
                    alt.Tooltip('amount:Q', title='支出額', format=',d')
                ]
            )

            # 3. 予算の赤ライン（目標金額）
            yield_df = pd.DataFrame({'threshold': [allowable_expense]})
            rule = alt.Chart(yield_df).mark_rule(
                color='#e45756', # 警告をイメージする赤色
                strokeDash=[5, 5],
                size=2
            ).encode(
                y='threshold:Q'
            )

            # 4. 合体させて表示
            # 縦軸の範囲を、支出が少なくても「予算ライン」まで見えるように自動調整
            combined_chart = (bars + rule).properties(
                height=400
            ).interactive() # 拡大・縮小もできるようにする

            st.write(monthly_summary)

            st.altair_chart(combined_chart, use_container_width=True)

        # --- これまでの円グラフや履歴表示のコードの下に追加 ---
        
            st.divider()
            st.subheader("✏️ 履歴の編集・削除")
        
            # 画面が長くなりすぎないよう、エキスパンダー（折りたたみメニュー）の中に入れる
            with st.expander("過去の記録を直接編集する"):
                st.info("💡 【操作方法】\n"
                        "・**編集**: セルをダブルクリックして直接書き換えます。\n"
                        "・**削除**: 行の左端にあるチェックボックスを選択し、キーボードの「Delete」キーを押します。")
            
                # Streamlitの強力なデータエディター機能
                # num_rows="dynamic" にすることで、行の追加・削除が可能になります
                edited_df = st.data_editor(
                    df_history,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="history_editor"
                )
            
            # 保存ボタンが押されたら、編集後のデータフレームでCSVを丸ごと上書きする
            if st.button("変更をデータベースに保存", type="primary"):
                target_file = get_db_filename(current_user)
                # 編集されたデータをCSVとして上書き保存
                edited_df.to_csv(target_file, index=False)
                st.success("✅ データベースを更新しました！")
                st.rerun() # 画面をリロードして、上のグラフや予算計算にも反映させる
