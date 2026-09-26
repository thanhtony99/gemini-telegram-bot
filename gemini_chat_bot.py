import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai
from google.genai import types

# 1. Lấy các biến môi trường cấu hình
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

# 2. Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# 3. Cấu hình ghi log hệ thống
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 4. Hàm xử lý tin nhắn từ người dùng Telegram
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Hiển thị trạng thái "đang gõ..." trên Telegram
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Gửi yêu cầu tới Gemini kèm công cụ Google Search thời gian thực
        response = client.models.generate_content(
            model='gemini-3.6-flash',  # Mô hình Gemini thế hệ mới
            contents=user_text,
            config=types.GenerateContentConfig(
                # Kích hoạt tính năng Google Search Grounding (Online)
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7,
            )
        )
        bot_reply = response.text if response.text else "Tôi không thể tìm thấy câu trả lời phù hợp."
    except Exception as e:
        bot_reply = f"Lỗi xử lý: {str(e)}"
        
    await update.message.reply_text(bot_reply)

# 5. Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Chào bạn! Tôi là Bot AI Gemini (Phiên bản Online kết nối Google Search). Hãy đặt câu hỏi cho tôi nhé!")

# 6. Khởi chạy ứng dụng
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Đăng ký các bộ xử lý lệnh và tin nhắn
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Kích hoạt Webhook cho Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
