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

# Chỉ thị hệ thống (System Instruction): Ép AI trả lời sâu, chi tiết và có cấu trúc
SYSTEM_INSTRUCTION = (
    "Bạn là một trợ lý AI cao cấp, thông minh và chuyên nghiệp. "
    "Hãy luôn phân tích kỹ lưỡng, trả lời đầy đủ, chi tiết, chính xác "
    "và sử dụng định dạng Markdown để trình bày đẹp mắt nhất cho người dùng."
)

# ==========================================
# 2. HÀM XỬ LÝ TIN NHẮN (FULL POWER & GOOGLE SEARCH)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Bật trạng thái "đang gõ..." trên Telegram
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    bot_reply = ""

    try:
        # ƯU TIÊN HÀNG ĐẦU: Luôn gọi Gemini 3.6 Flash KÈM Google Search cho MỌI câu hỏi
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(google_search=types.GoogleSearch())], # Bật Search 100%
                temperature=0.7,
            )
        )
        bot_reply = response.text if response.text else "Không nhận được phản hồi từ AI."

    except Exception as e:
        error_message = str(e)
        logging.warning(f"Lỗi khi gọi API Search Trực tuyến: {error_message}")

        # DỰ PHÒNG CHỐNG SỰ CỐ: Nếu hết hạn mức Google Search (Lỗi 429), gọi chế độ thường
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
                    f"⚠️ *(Lưu ý: Do vừa chạm trần giới hạn Google Search tạm thời trong phút này, "
                    f"câu trả lời trên được xuất ra từ tri thức sẵn có của Gemini 3.6 Flash)*"
                )
            except Exception as fallback_error:
                bot_reply = "⚠️ Hệ thống đang quá tải lượt truy cập API trong phút này. Bạn vui lòng chờ khoảng 1 phút rồi gửi lại nhé!"
        else:
            bot_reply = f"Lỗi xử lý hệ thống: {error_message}"

    # Gửi câu trả lời về Telegram (Cho phép hiển thị Markdown)
    await update.message.reply_text(bot_reply, parse_mode='Markdown')

# ==========================================
# 3. LỆNH KHỞI ĐỘNG BOT (/start)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Bot AI Gemini 3.6 Flash - Chế Độ Tối Đa Công Suất**\n\n"
        "• Tự động tra cứu Google Search thời gian thực cho **tất cả** câu hỏi.\n"
        "• Phân tích sâu, chi tiết và chính xác nhất.\n\n"
        "Hãy gửi câu hỏi cho tôi ngay nhé!"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# ==========================================
# 4. CHƯƠNG TRÌNH CHÍNH (WEBHOOK DEPLOY)
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
