import smtplib
import os
import time
import random
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定日誌 (Logging) ---
# 這樣在 GitHub Actions 的 Console 可以清楚看到誰成功、誰失敗
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 環境變數 ---
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")

# 修改為你實際的 Sheet 名稱 (根據你的截圖)
SHEET_NAME = "訂閱我的電子報"

# --- 信件內容設定 ---
EMAIL_SUBJECT = "【新文章通知】我的部落格更新囉！"
# 建議使用 HTML 讓信件更專業
EMAIL_CONTENT_HTML = """
<html>
  <body>
    <h2>👋 哈囉！</h2>
    <p>我的部落格剛發布了一篇新文章，誠摯邀請您來閱讀。</p>
    <p><a href="https://your-blog-url.com" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">點此閱讀文章</a></p>
    <hr>
    <p style="font-size: 12px; color: gray;">如果您不想再收到此通知，請回信告知。</p>
  </body>
</html>
"""

def get_subscribers():
    """從 Google Sheet 讀取訂閱者清單"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(CREDENTIALS_JSON), scope)
        client = gspread.authorize(creds)
        
        # 開啟指定的 Sheet
        sheet = client.open(SHEET_NAME).sheet1
        
        # 取得第二欄的所有 Email (假設第一列是標題)
        # col_values(2) 代表讀取 B 欄
        emails = sheet.col_values(2)
        
        # 去除空白、重複，並跳過標題列 (假設 index 0 是標題 "Email Address")
        # emails[1:] 代表從第 2 列開始讀取 (跳過標題)
        valid_emails = list(set([e.strip() for e in emails[1:] if e.strip()]))
        
        logging.info(f"成功讀取到 {len(valid_emails)} 個不重複的 Email。")
        return valid_emails
    except Exception as e:
        logging.error(f"讀取 Google Sheet 失敗: {e}")
        # 如果失敗，印出更多資訊幫助除錯
        logging.error(f"請確認 Sheet 名稱是否為 '{SHEET_NAME}'，且機器人有編輯權限。")
        return []

def send_emails(subscriber_list):
    """執行寄信迴圈，包含錯誤處理與速率限制"""
    
    if not subscriber_list:
        logging.warning("沒有訂閱者，結束程式。")
        return

    # 建立 SMTP 連線
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(GMAIL_USER, GMAIL_PASS)
        logging.info("SMTP 登入成功。")
    except Exception as e:
        logging.error(f"SMTP 連線失敗: {e}")
        return

    count = 0
    BATCH_SIZE = 20  # 每寄 20 封重新連線一次 (避免長時間連線被斷)

    for email in subscriber_list:
        try:
            # 1. 建立信件物件 (每次都要重新建立)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = EMAIL_SUBJECT
            msg["From"] = formataddr(("部落格通知機器人", GMAIL_USER))
            msg["To"] = email
            
            # 加入 HTML 內容
            msg.attach(MIMEText(EMAIL_CONTENT_HTML, "html"))

            # 2. 執行發送
            server.sendmail(GMAIL_USER, email, msg.as_string())
            logging.info(f"[{count+1}/{len(subscriber_list)}] 成功寄給: {email}")
            count += 1

            # 3. 速率限制 (Rate Limiting) - 重要！
            # 隨機等待 2 到 5 秒，模擬人類行為，避免被 Gmail 判定為濫發
            sleep_time = random.uniform(2, 5)
            time.sleep(sleep_time)

            # 4. 批次重連機制 (防止 Connection Timeout)
            if count % BATCH_SIZE == 0:
                logging.info("達到批次上限，重新建立 SMTP 連線...")
                server.quit()
                time.sleep(5) # 休息一下
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                server.login(GMAIL_USER, GMAIL_PASS)

        except Exception as e:
            # 捕捉單一信件發送失敗，但不中斷迴圈
            logging.error(f"寄給 {email} 失敗: {e}")
            continue

    # 結束後關閉連線
    try:
        server.quit()
    except:
        pass
    logging.info("所有信件處理完成。")

if __name__ == "__main__":
    logging.info("開始執行通知腳本...")
    subscribers = get_subscribers()
    if subscribers:
        send_emails(subscribers)