import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai
from google.genai import types

# ==========================================
# 1. KHAI BÁO BIẾN MÔI TRƯỜNG & HỆ THỐNG
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình nhật ký hệ thống (Logging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Chỉ thị hệ thống giúp AI trả lời chi tiết và chuyên nghiệp
SYSTEM_INSTRUCTION = (
    "Bạn là một trợ lý AI cao cấp, thông minh và chuyên nghiệp. "
    "Hãy luôn phân tích kỹ lưỡng, trả lời đầy đủ, chi tiết, chính xác "
    "và sử dụng định dạng rõ ràng để trình bày cho người dùng."
)

# ==========================================
# 2. HÀM GỬI TIN NHẮN AN TOÀN (CHỐNG TRÔI TIN)
# ==========================================
async def safe_reply(update: Update, text: str):
    """
    Hàm hỗ trợ gửi tin nhắn an toàn:
    Thử gửi bằng Markdown trước, nếu Telegram báo lỗi ký tự sẽ tự động chuyển sang Plain Text.
    """
    try:
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logging.warning(f"Lỗi parse Markdown ({e}), chuyển sang gửi Plain Text.")
        try:
            await update.message.reply_text(text)
        except Exception as final_err:
            logging.error(f"Không thể gửi tin nhắn Telegram: {final_err}")

# ==========================================
# 3. HÀM XỬ LÝ TIN NHẮN CHÍNH
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logging.info(f"Nhận tin nhắn từ người dùng: {user_text}")
    
    # Hiển thị biểu tượng "đang gõ..." trên Telegram
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception as e:
        logging.warning(f"Không thể gửi chat action: {e}")
    
    bot_reply = ""

    try:
        # Gọi Gemini 3.6 Flash kèm Google Search Trực tuyến cho 100% câu hỏi
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7,
            )
        )
        bot_reply = response.text if response.text else "Không nhận được phản hồi từ AI."

    except Exception as e:
        error_message = str(e)
        logging.error(f"Lỗi khi gọi Gemini API: {error_message}")

        # Tự động xử lý khi hết Quota Google Search (Lỗi 429)
        if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
            try:
                response_fallback = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                    )
                )
                bot_reply = (
                    f"{response_fallback.text}\n\n"
                    f"⚠️ *(Lưu ý: Tạm thời đạt giới hạn Google Search, câu trả lời dựa trên tri thức sẵn có của AI)*"
                )
            except Exception as fallback_error:
                bot_reply = "⚠️ Hệ thống đang quá tải Quota API trong phút này. Bạn vui lòng đợi 1 phút rồi gửi lại nhé!"
        else:
            bot_reply = f"Đã xảy ra lỗi hệ thống: {error_message}"

    # Gửi câu trả lời an toàn về Telegram
    await safe_reply(update, bot_reply)

# ==========================================
# 4. LỆNH KHỞI ĐỘNG BOT (/start)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = "🚀 Chào bạn! Bot AI Gemini đã sẵn sàng hỗ trợ. Hãy gửi câu hỏi cho tôi nhé!"
    await safe_reply(update, welcome_text)

# ==========================================
# 5. CHƯƠNG TRÌNH CHÍNH (WEBHOOK DEPLOY)
# ==========================================
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
