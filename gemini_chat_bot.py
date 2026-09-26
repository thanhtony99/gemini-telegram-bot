import os
import logging
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

# Tên mô hình chính thức của Google Gemini API
MODEL_NAME = 'gemini-2.5-flash'

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình nhật ký hệ thống (Logging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Chỉ thị hệ thống (System Instruction): Ép AI đóng vai chuyên gia trả lời sâu sắc và chi tiết
SYSTEM_INSTRUCTION = (
    "Bạn là một trợ lý AI cao cấp, thông minh, chuyên về lập trình và giải quyết vấn đề. "
    "Hãy luôn phân tích kỹ lưỡng, trả lời đầy đủ, chi tiết, chính xác "
    "và trình bày bằng định dạng Markdown đẹp mắt, rõ ràng."
)

# ==========================================
# 2. HÀM GỬI TIN NHẮN AN TOÀN (SAFE REPLY)
# ==========================================
async def safe_reply(update: Update, text: str):
    """
    Gửi tin nhắn về Telegram an toàn.
    Thử định dạng Markdown trước; nếu gặp lỗi ký tự đặc biệt sẽ tự động gửi dạng Plain Text.
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
# 3. HÀM XỬ LÝ LỘC CÂU HỎI & GỌI GEMINI API
# ==========================================
async def process_gemini_request(user_text: str, enable_search: bool = False) -> str:
    """
    Hàm gọi Gemini API với chế độ Offline (mặc định) hoặc Online (khi dùng lệnh /search)
    """
    config_params = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "temperature": 0.7,
    }
    
    # Chỉ đính kèm Google Search khi enable_search = True
    if enable_search:
        config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_text,
            config=types.GenerateContentConfig(**config_params)
        )
        return response.text if response.text else "Không nhận được phản hồi từ AI."
        
    except Exception as e:
        err_msg = str(e)
        logging.error(f"Lỗi API Gemini (Search={enable_search}): {err_msg}")
        
        # Nếu đang bật Search mà bị lỗi 429 Quota, tự động chuyển ngay sang Chế độ Offline
        if enable_search and ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg):
            logging.info("Tự động chuyển sang chế độ Offline do hết Quota Search...")
            try:
                response_offline = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7
                    )
                )
                return (
                    f"{response_offline.text}\n\n"
                    f"💡 *(Lưu ý: Đã đạt hạn mức Google Search hôm nay. "
                    f"Câu trả lời được xuất ra từ tri thức chuyên sâu sẵn có của Gemini)*"
                )
            except Exception as fallback_err:
                return f"⚠️ Lỗi hệ thống: {fallback_err}"
        
        return f"⚠️ Đã xảy ra lỗi: {err_msg}"

# ==========================================
# 4. HANDLERS XỬ LÝ TIN NHẮN TELEGRAM
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý các tin nhắn chat thông thường (Chế độ mặc định siêu nhanh)"""
    user_text = update.message.text
    logging.info(f"Nhận tin nhắn thường: {user_text}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Mặc định sử dụng Chế độ Tri thức Chuyên sâu (Phản hồi tức thì, không tốn Quota Search)
    bot_reply = await process_gemini_request(user_text, enable_search=False)
    await safe_reply(update, bot_reply)

async def handle_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng dùng lệnh /search hoặc /s để tra cứu online"""
    user_text = " ".join(context.args) if context.args else ""
    
    if not user_text:
        await safe_reply(
            update, 
            "🔍 **Cách dùng lệnh Search Online:**\n"
            "Cú pháp: `/search <câu hỏi>` hoặc `/s <câu hỏi>`\n"
            "Ví dụ: `/search thời tiết TP HCM hôm nay`"
        )
        return

    logging.info(f"Nhận yêu cầu Search Online: {user_text}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Bật Google Search Trực tuyến cho riêng câu hỏi này
    bot_reply = await process_gemini_request(user_text, enable_search=True)
    await safe_reply(update, bot_reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Chào bạn! Tôi là Bot AI Gemini 2.5 Flash**\n\n"
        "• **Chat thông thường:** Hãy gửi câu hỏi trực tiếp (Viết code, sửa lỗi, giải thích mã,...). Phản hồi siêu nhanh và không bao giờ bị nghẽn Quota!\n"
        "• **Tra cứu Google Trực tuyến:** Dùng lệnh `/search <câu hỏi>` hoặc `/s <câu hỏi>` khi cần tra tin tức hay thông tin thời gian thực.\n\n"
        "Hãy gửi tin nhắn cho tôi ngay nhé!"
    )
    await safe_reply(update, welcome_text)

# ==========================================
# 5. CHƯƠNG TRÌNH CHÍNH (WEBHOOK DEPLOYMENT)
# ==========================================
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Đăng ký lệnh
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('search', handle_search_command))
    app.add_handler(CommandHandler('s', handle_search_command))
    
    # Tin nhắn văn bản thông thường
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Khởi chạy Webhook trên Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
