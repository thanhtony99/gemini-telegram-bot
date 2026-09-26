import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai
from google.genai import types

# ==========================================
# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG & HỆ THỐNG
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Danh sách định danh mô hình chuẩn xác của Google Gemini API
SEARCH_CASCADE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash-lite'
]

# Mô hình sử dụng cho dữ liệu nội bộ (Offline Data)
OFFLINE_FALLBACK_MODEL = 'gemini-3.8-flash'

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình Nhật ký Hệ thống (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# Chỉ thị hệ thống
SYSTEM_INSTRUCTION = (
    "Bạn là một trợ lý AI cao cấp, thông minh, chuyên về lập trình và giải quyết vấn đề. "
    "Hãy luôn phân tích kỹ lưỡng, trả lời đầy đủ, chi tiết, chính xác "
    "và trình bày bằng định dạng Markdown đẹp mắt, rõ ràng."
)

# ==========================================
# 2. HÀM GỬI TIN NHẮN AN TOÀN
# ==========================================
async def safe_reply(update: Update, text: str):
    """Gửi tin nhắn về Telegram an toàn, tự động phòng ngừa lỗi định dạng Markdown."""
    try:
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logging.warning(f"Lỗi parse Markdown ({e}), chuyển sang gửi Plain Text.")
        try:
            await update.message.reply_text(text)
        except Exception as final_err:
            logging.error(f"Không thể gửi tin nhắn Telegram: {final_err}")

# ==========================================
# 3. HÀM XỬ LÝ CHUỖI FALLBACK MÔ HÌNH
# ==========================================
async def process_gemini_request(user_text: str, enable_search: bool = True) -> str:
    """
    Thực hiện gọi API theo chuỗi Fallback mô hình chuẩn:
    3.8 Flash (Online) -> 3.7 Flash (Online) -> 3.6 Flash (Online) -> 3.5 Flash Lite (Online)
    -> 3.8 Flash (Offline Data)
    """
    
    # BƯỚC 1: Thử lần lượt các mô hình ở Chế độ Search Online
    if enable_search:
        for model_name in SEARCH_CASCADE_MODELS:
            try:
                logging.info(f"Đang thử tra cứu Google Search với mô hình: {model_name}")
                
                config_search = types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                
                # Gọi API bất đồng bộ
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_text,
                    config=config_search
                )
                
                if response and response.text:
                    logging.info(f"Thành công lấy dữ liệu Search từ mô hình: {model_name}")
                    return response.text

            except Exception as e:
                # Ghi nhận lỗi chi tiết ra Log trên Render để kiểm tra
                logging.warning(f"Mô hình '{model_name}' gặp lỗi khi Search: {e}")
                continue

    # BƯỚC 2: Fallback về Chế độ Offline (Dữ liệu tri thức sẵn có)
    logging.info(f"Tất cả mô hình Search Online không khả dụng. Chuyển sang Offline Data với {OFFLINE_FALLBACK_MODEL}")
    try:
        config_offline = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7
        )
        
        response_offline = await client.aio.models.generate_content(
            model=OFFLINE_FALLBACK_MODEL,
            contents=user_text,
            config=config_offline
        )
        
        if response_offline and response_offline.text:
            return (
                f"{response_offline.text}\n\n"
                f"💡 *(Lưu ý: Tính năng tìm kiếm trực tuyến tạm thời không khả dụng. "
                f"Câu trả lời dựa trên tri thức sẵn có của {OFFLINE_FALLBACK_MODEL})*"
            )

    except Exception as e_offline:
        logging.error(f"Lỗi khi gọi Offline Fallback: {e_offline}")

    return "⌛ Máy chủ Google AI hiện đang quá tải. Bạn vui lòng thử lại sau ít phút nhé!"

# ==========================================
# 4. HANDLERS XỬ LÝ TIN NHẮN
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logging.info(f"Nhận câu hỏi từ người dùng: {user_text}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    bot_reply = await process_gemini_request(user_text, enable_search=True)
    await safe_reply(update, bot_reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Bot Gemini AI đã được nâng cấp!**\n\n"
        "Hệ thống đã cập nhật danh sách mô hình chuẩn định danh API.\n"
        "Hãy đặt câu hỏi tìm kiếm cho tôi ngay nhé!"
    )
    await safe_reply(update, welcome_text)

# ==========================================
# 5. KHỞI CHẠY BOT (WEBHOOK)
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
