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

# Cấu hình danh sách mô hình (Mô hình chính & Mô hình dự phòng)
PRIMARY_MODEL = 'gemini-3.8-flash'
FALLBACK_MODEL = 'gemini-3.6-flash'

# Cấu hình tính năng Tự động Thử lại
MAX_RETRIES = 3      # Số lần thử lại tối đa cho mỗi mô hình
BASE_DELAY = 1.0     # Thời gian chờ cơ sở (giây)

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# System Instruction
SYSTEM_INSTRUCTION = (
    "Bạn là một trợ lý AI cao cấp, thông minh, chuyên về lập trình và giải quyết vấn đề. "
    "Hãy luôn phân tích kỹ lưỡng, trả lời đầy đủ, chi tiết, chính xác "
    "và trình bày bằng định dạng Markdown đẹp mắt, rõ ràng."
)

# ==========================================
# 2. HÀM GỬI TIN NHẮN AN TOÀN (SAFE REPLY)
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
# 3. HÀM GỌI GEMINI API BẤT ĐỒNG BỘ (ASYNC + FALLBACK)
# ==========================================
async def process_gemini_request(user_text: str, enable_search: bool = False) -> str:
    """
    Hàm gọi Gemini API bất đồng bộ với cơ chế Fallback sang Model dự phòng
    và Auto-Retry khi máy chủ bị quá tải (Lỗi 503/429).
    """
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model_name in models_to_try:
        config_params = {
            "system_instruction": SYSTEM_INSTRUCTION,
            "temperature": 0.7,
        }
        
        if enable_search:
            config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Sử dụng client.aio (Async Client) để không gây nghẽn event loop của Telegram
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_text,
                    config=types.GenerateContentConfig(**config_params)
                )
                
                if response and response.text:
                    return response.text
                
            except Exception as e:
                err_msg = str(e)
                logging.warning(f"Thử model '{model_name}' (Lần {attempt}/{MAX_RETRIES}) gặp lỗi: {err_msg}")
                
                # Kiểm tra lỗi quá tải 503 hoặc hết hạn mức 429
                is_overload = any(code in err_msg for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"])
                
                if is_overload:
                    if attempt < MAX_RETRIES:
                        wait_time = BASE_DELAY * (2 ** (attempt - 1)) # 1s, 2s, 4s
                        logging.info(f"Đang chờ {wait_time}s trước khi thử lại...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logging.info(f"Model '{model_name}' quá tải hoàn toàn. Tự động chuyển sang mô hình dự phòng...")
                        break # Chuyển sang model tiếp theo trong models_to_try
                else:
                    # Lỗi khác (ví dụ sai cú pháp) -> Dừng ngay
                    break

    return "⌛ Máy chủ Google AI hiện đang trong đợt bảo trì/quá tải tạm thời trên toàn hệ thống. Bạn vui lòng thử lại sau ít phút nhé!"

# ==========================================
# 4. HANDLERS XỬ LÝ TIN NHẮN TELEGRAM
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý câu hỏi thông thường (Chế độ mặc định - Phản hồi tức thì)"""
    user_text = update.message.text
    logging.info(f"Nhận tin nhắn: {user_text}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    bot_reply = await process_gemini_request(user_text, enable_search=False)
    await safe_reply(update, bot_reply)

async def handle_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tra cứu online khi dùng lệnh /search hoặc /s"""
    user_text = " ".join(context.args) if context.args else ""
    
    if not user_text:
        await safe_reply(
            update, 
            "🔍 **Cách dùng lệnh Tra cứu Online:**\n"
            "Cú pháp: `/search <câu hỏi>` hoặc `/s <câu hỏi>`\n"
            "Ví dụ: `/s giá xăng hôm nay`"
        )
        return

    logging.info(f"Nhận yêu cầu Search Online: {user_text}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    bot_reply = await process_gemini_request(user_text, enable_search=True)
    await safe_reply(update, bot_reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Chào bạn! Tôi là Bot AI Gemini (Bản ổn định chống quá tải)**\n\n"
        "• **Hỏi đáp lập trình:** Nhắn tin trực tiếp để trao đổi về mã code, tư vấn logic.\n"
        "• **Tra cứu Online:** Dùng lệnh `/s <câu hỏi>` hoặc `/search <câu hỏi>`.\n\n"
        "Hãy gửi tin nhắn cho tôi nhé!"
    )
    await safe_reply(update, welcome_text)

# ==========================================
# 5. CHƯƠNG TRÌNH CHÍNH (WEBHOOK DEPLOYMENT)
# ==========================================
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Đăng ký các Handler
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('search', handle_search_command))
    app.add_handler(CommandHandler('s', handle_search_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Khởi chạy Webhook trên Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
