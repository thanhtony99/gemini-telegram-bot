import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai
from google.genai import types

# 1. Khai báo các biến môi trường
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

# 2. Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# 3. Cấu hình Log hệ thống
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 4. Hàm xử lý tin nhắn chính
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Bật trạng thái "đang gõ..." trên Telegram
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    bot_reply = ""
    
    try:
        # LẦN 1: Gọi Gemini 3.6 Flash kèm Google Search Trực tuyến
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7,
            )
        )
        bot_reply = response.text if response.text else "Không tìm thấy nội dung phản hồi."

    except Exception as e:
        error_message = str(e)
        logging.warning(f"Lỗi khi gọi API Search: {error_message}")
        
        # Xử lý tự động khi gặp lỗi vọt hạn mức Quota (429)
        if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
            try:
                # LẦN 2 (FALLBACK): Gọi Gemini 3.6 Flash ở chế độ thường (Không dùng Search)
                response_fallback = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=user_text
                )
                bot_reply = (
                    f"{response_fallback.text}\n\n"
                    f"⚠️ *(Lưu ý: Do hết hạn mức tìm kiếm Google Search tạm thời, "
                    f"câu trả lời này dựa trên tri thức có sẵn của AI)*"
                )
            except Exception as fallback_error:
                bot_reply = "⚠️ Hệ thống đang quá tải quota Gemini API (Lỗi 429). Bạn vui lòng chờ 1-2 phút rồi thử lại nhé!"
        else:
            bot_reply = f"Lỗi xử lý hệ thống: {error_message}"

    await update.message.reply_text(bot_reply)

# 5. Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Chào bạn! Tôi là Bot AI Gemini (Phiên bản Gemini 3.6 Flash). Hãy gửi câu hỏi cho tôi nhé!")

# 6. Khởi chạy Bot Webhook
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
