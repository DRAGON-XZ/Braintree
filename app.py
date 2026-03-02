import asyncio
import time
import json
import logging
import threading
import os
from flask import Flask, jsonify
from pyrogram import Client

API_ID = 34231766
API_HASH = "04adf4bfb194961bb25c3cd44f2726e6"
SESSION_STRING = "BAIKVdYAJtmZgYBX-p2UaNHLyXQtorE4ONGgYa1We9L9w1zCjpwZdHmXr_LR_cvNR2uwIkn5f6y5HsCNFA7Ou17s0MvhtHJQEnXYL5Lp3xUD3W62DN-iTGtsoSYwSncltdnPco7DIlA6v2PDg1RPgWUNu82c4e1QLA1FMLjAGycUZ1Em6Z4_XX3j3qiUNR8KEAizdBRRuNcLQiWuewtzl48YRQoaqHO_aOe8zy5npfkiRvjhx_cRWWE5S4oc-djlxYZ5inPPi8PZHQesWiQ66bB1EL4ci7xVkU6unf4zhz48wh_5FXsJo1lx1_z94I8zyLcOB5joilBsh4P1DwGR1iLGQQmslQAAAAGkGqEOAA"
TARGET_BOT = "@SSCCGenbot"

app = Flask(__name__)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.CRITICAL)

loop = None
pyrogram_client = None
startup_event = threading.Event()


def run_pyrogram_background():
    global loop, pyrogram_client

    if not API_ID or not API_HASH or not SESSION_STRING:
        logger.critical("Missing API_ID, API_HASH, or SESSION_STRING.")
        startup_event.set()
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Background thread: Loop created.")

    async def start_client():
        global pyrogram_client
        pyrogram_client = Client(
            name="user_session",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=SESSION_STRING,
            in_memory=True
        )
        await pyrogram_client.start()
        logger.info("Background thread: Pyrogram Connected Successfully.")
        startup_event.set()

    try:
        loop.run_until_complete(start_client())
        loop.run_forever()
    except Exception as e:
        logger.critical(f"Background thread: Failed to start - {e}")
        logger.critical("Check if your Session String is valid/banned.")
        startup_event.set()


t = threading.Thread(target=run_pyrogram_background, daemon=True)
t.start()


async def get_card_response(cc_number):
    try:
        if not pyrogram_client or not pyrogram_client.is_connected:
            raise Exception("Pyrogram client is disconnected")

        logger.info(f"Sending /chk {cc_number} to {TARGET_BOT}...")
        await pyrogram_client.send_message(TARGET_BOT, f"/chk {cc_number}")

        logger.info("Command sent. Waiting 10 seconds...")
        await asyncio.sleep(10)

        logger.info("Fetching chat history...")
        async for message in pyrogram_client.get_chat_history(TARGET_BOT, limit=1):
            full_text = message.text or ""

            import unicodedata
            normalized = unicodedata.normalize("NFKC", full_text)

            extracted = "No response found"
            for line in normalized.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("response:"):
                    extracted = stripped.split(":", 1)[1].strip()
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


@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "usage": "/gate=b3/cc=<cc_details>"
    })


@app.route('/gate=b3/cc=<path:cc_details>')
def check_gate_b3(cc_details):
    try:
        start_time = time.time()

        if cc_details.startswith("="):
            cc_details = cc_details[1:]

        logger.info(f"--- New Request ---")
        logger.info(f"Card Details: {cc_details}")

        if not startup_event.is_set():
            logger.warning("Pyrogram not ready yet. Waiting...")
            startup_event.wait(timeout=10)

        if loop is None or pyrogram_client is None:
            return jsonify({"error": "Service Unavailable: Userbot not initialized"}), 503

        future = asyncio.run_coroutine_threadsafe(get_card_response(cc_details), loop)
        raw_response = future.result(timeout=30)

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
