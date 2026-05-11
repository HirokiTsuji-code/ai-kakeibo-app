# 🛡️ AI家計簿システム (AI-Powered Household Account Book)

## 📝 概要 (Overview)
Google Cloud Vision APIを活用し、レシートや決済アプリの履歴画像から自動で支出を読み取り、カテゴライズ・分析を行うSaaS型の家計簿アプリケーションです。手入力を極限まで減らし、直感的なダッシュボードで支出を管理できます。

## ✨ 主な機能 (Features)
- 📸 **AI OCR読み取り**: カメラ撮影・画像アップロードからレシートやPayPay履歴を自動解析
- 🧠 **Human-in-the-Loop自動分類**: 未知の店舗をユーザーに選ばせ辞書として学習。次回以降は自動カテゴライズ
- 🔐 **セキュアな認証**: ユーザーごとのデータ独立管理（マルチテナント）とパスワードハッシュ化
- 📊 **ダッシュボード＆カレンダー**: 今月の支出、円グラフ、カレンダーへのシームレスな可視化
- ✏️ **直感的なデータ編集**: Data Editor機能を用いたExcelライクなバルク（一括）編集・削除

## 🛠 技術スタック (Tech Stack)
- **Frontend / Backend**: Python, Streamlit
- **AI / OCR**: Google Cloud Vision API
- **Data Analysis**: Pandas, Altair
- **Testing**: Pytest

## 🚀 ローカルでの起動方法 (How to Run)
1. リポジトリをクローン
2. `pip install -r requirements.txt` を実行
3. `.streamlit/secrets.toml` を作成し、`GOOGLE_API_KEY` を設定
4. `streamlit run app.py` で起動