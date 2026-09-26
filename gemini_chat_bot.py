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

# Danh sách chuỗi Fallback Tra cứu Online theo đúng thứ tự ưu tiên
SEARCH_CASCADE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash-lite'
]

# Mô hình sử dụng cho dữ liệu nội bộ (Offline Data) khi tất cả Quota Search đã hết
OFFLINE_FALLBACK_MODEL = 'gemini-3.8-flash'

# Khởi tạo Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình Nhật ký Hệ thống (Logging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Chỉ thị hệ thống (System Instruction)
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
# 3. HÀM THỰC HIỆN CHUỖI FALLBACK WATERFALL
# ==========================================
async def process_gemini_request(user_text: str, enable_search: bool = True) -> str:
    """
    Hàm thực hiện chuỗi Fallback linh hoạt:
    3.8 Flash (Online) -> 3.7 Flash (Online) -> 3.6 Flash (Online) -> 3.5 Flash Lite (Online)
    -> 3.8 Flash (Offline Data)
    """
    
    # ----------------------------------------------------
    # BƯỚC 1: Thử lần lượt các mô hình ở Chế độ Search Online
    # ----------------------------------------------------
    if enable_search:
        for model_name in SEARCH_CASCADE_MODELS:
            try:
                logging.info(f"Đang thử tra cứu Online với mô hình: {model_name}")
                
                config_search = types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                
                # Gọi API bất đồng bộ với Google Search
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=user_text,
                    config=config_search
                )
                
                if response and response.text:
                    logging.info(f"Thành công lấy dữ liệu Online từ model: {model_name}")
                    return response.text

            except Exception as e:
                logging.warning(f"Mô hình '{model_name}' (Online Search) gặp lỗi/hết Quota: {e}")
                # Tiếp tục vòng lặp để nhảy sang mô hình tiếp theo trong SEARCH_CASCADE_MODELS
                continue

    # ----------------------------------------------------
    # BƯỚC 2: Fallback về 3.8 Flash Chế độ Offline (Tri thức sẵn có)
    # ----------------------------------------------------
    logging.info(f"Tất cả mô hình Search Online đều hết Quota/Lỗi. Chuyển sang Offline Data với {OFFLINE_FALLBACK_MODEL}")
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
                f"💡 *(Lưu ý: Hạn mức tra cứu Google Online của tất cả các mô hình hôm nay đã hết. "
                f"Câu trả lời được trích xuất từ tri thức sẵn có của {OFFLINE_FALLBACK_MODEL})*"
            )

    except Exception as e_offline:
        logging.error(f"Lỗi khi gọi Offline Fallback {OFFLINE_FALLBACK_MODEL}: {e_offline}")
        
        # Dự phòng khẩn cấp cuối cùng: Dùng 3.5 Flash Lite Offline
        try:
            response_last = await client.aio.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=user_text,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            )
            return response_last.text
        except Exception as final_err:
            logging.error(f"Lỗi khẩn cấp toàn hệ thống: {final_err}")

    return "⌛ Máy chủ Google AI hiện đang quá tải toàn bộ các mô hình. Bạn vui lòng thử lại sau ít phút nhé!"

# ==========================================
# 4. HANDLERS XỬ LÝ TIN NHẮN TELEGRAM
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mặc định mỗi câu hỏi gửi lên đều chạy qua chuỗi Fallback Search Online"""
    user_text = update.message.text
    logging.info(f"Nhận câu hỏi: {user_text}")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Kích hoạt chuỗi Fallback ưu tiên Search Online
    bot_reply = await process_gemini_request(user_text, enable_search=True)
    await safe_reply(update, bot_reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🚀 **Chào bạn! Tôi là Bot AI Gemini (Bản Tối ưu Chuỗi Fallback)**\n\n"
        "• Hệ thống tự động tìm kiếm kết quả tốt nhất qua chuỗi mô hình: **3.8 Flash ➔ 3.7 Flash ➔ 3.6 Flash ➔ 3.5 Flash Lite**.\n"
        "• Nếu tất cả các mô hình hết hạn mức Search Online, hệ thống sẽ tự động dùng dữ liệu tri thức sẵn có của **Gemini 3.8 Flash**.\n\n"
        "Hãy đặt câu hỏi cho tôi ngay nhé!"
    )
    await safe_reply(update, welcome_text)

# ==========================================
# 5. CHƯƠNG TRÌNH CHÍNH (WEBHOOK DEPLOYMENT)
# ==========================================
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Đăng ký các Handler
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # Khởi chạy Webhook trên Render
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )
