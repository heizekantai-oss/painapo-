# 1. ベースとなる画像（Python 3.10 が入った軽量Linux）を取得
FROM python:3.10-slim

# 2. コンテナ内の作業ディレクトリを設定
WORKDIR /app

# 3. 必要なファイルをコンテナ内にコピー
# (requirements.txt を先にコピーしてインストールするとキャッシュが効いて高速化します)
COPY requirements.txt .

# 4. ライブラリをインストール
# (--no-cache-dir はイメージサイズを小さくするためのおまじないです)
RUN pip install --no-cache-dir -r requirements.txt

# 5. ソースコード一式をコピー
COPY . .

# 6. アプリが使うポート番号を指定（Streamlitはデフォルト8501）
EXPOSE 8501

# 7. コンテナ起動時に実行するコマンド
CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0"]