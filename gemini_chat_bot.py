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

# Danh sách chuỗi mô hình ưu tiên cho Search Online (3.8 -> 3.7 -> 3.6 -> 3.5 Lite)
SEARCH_CASCADE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash-lite'
]

# Mô hình sử dụng cho dữ liệu nội bộ (Offline Data)
OFFLINE_MODEL = 'gemini-3.8-flash'

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình Logging
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
    """Gửi tin nhắn về Telegram an toàn, tránh lỗi văng do định dạng Markdown."""
    try:
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logging.warning(f"Lỗi parse Markdown ({e}), chuyển sang gửi Plain Text.")
        try:
            await update.message.reply_text(text)
        except Exception as final_err:
            logging.error(f"Không thể gửi tin nhắn Telegram: {final_err}")

# ==========================================
# 3. HÀM CHUỖI FALLBACK MÔ HÌNH (3.8 -> 3.5 & 3.8 OFFLINE)
# ==========================================
async def process_gemini_request(user_text: str) -> str:
    """
    Thực hiện gọi API theo thứ tự:
    3.8 Flash (Online) -> 3.7 Flash (Online) -> 3.6 Flash (Online) -> 3.5 Flash Lite (Online)
    -> 3.8 Flash (Offline Data)
    """
    
    # BƯỚC 1: Thử lần lượt các mô hình từ 3.8 đến 3.5 Lite ở Chế độ Search Online
    for model_name in SEARCH_CASCADE_MODELS:
        try:
            logging.info(f"Đang thử tra cứu Google Search với mô hình: {model_name}")
            
            config_search = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
            
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=user_text,
                config=config_search
            )
            
            if response and response.text:
                logging.info(f"Thành công lấy dữ liệu Search từ mô hình: {model_name}")
                return response.text

        except Exception as e:
            logging.warning(f"Mô hình '{model_name}' gặp lỗi khi Search: {e}")
            # Nghỉ 1 giây để tránh lỗi gọi dồn dập (Burst Rate Limit)
            await asyncio.sleep(1)
            continue

    # BƯỚC 2: Fallback về gemini-3.8-flash Chế độ Offline (Tri thức sẵn có)
    logging.info(f"Tất cả mô hình Search Online không khả dụng. Chuyển sang dữ liệu Offline với {OFFLINE_MODEL}")
    try:
        config_offline = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7
        )
        
        response_offline = await client.aio.models.generate_content(
            model=OFFLINE_MODEL,
            contents=user_text,
            config=config_offline
        )
        
        if response_offline and response_offline.text:
            return (
                f"{response_offline.text}\n\n"
                f"💡 *(Lưu ý: Hạn mức tra cứu Google Search trực tuyến hôm nay đã hết. "
                f"Câu trả lời được trích xuất từ tri thức sẵn có của {OFFLINE_MODEL})*"
            )

    except Exception as e_offline:
        logging.error(f"Lỗi khi gọi Offline Fallback {OFFLINE_MODEL}: {e_offline}")

    return "⌛ Máy chủ Google AI hiện đang quá tải. Bạn vui lòng thử lại sau ít phút nhé!"

# ==========================================
# 4. HANDLERS VÀ KHỞI CHẠY BOT
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logging.info(f"Nhận câu hỏi: {user_text}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    bot_reply = await process_gemini_request(user_text)
    await safe_reply(update, bot_reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Bot Gemini AI đã được cập nhật!**\n\n"
        "Chuỗi Fallback tra cứu hiện tại: **3.8 Flash ➔ 3.7 Flash ➔ 3.6 Flash ➔ 3.5 Flash Lite ➔ 3.8 Flash Offline**.\n"
        "Hãy gửi câu hỏi cho tôi ngay nhé!"
    )
    await safe_reply(update, welcome_text)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
