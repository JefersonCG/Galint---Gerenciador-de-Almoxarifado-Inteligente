
import sys
import threading
import time
import logging
from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.services.telegram_service import TelegramService
from galint_flask.models import TelegramOutbox, TelegramNotification

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

def test_dedupe():
    with app.app_context():
        # Clean up previous test data
        chat_id = "123456789"
        msg_text = f"Test Message {time.time()}"
        
        # CLEAR old messages for this chat (optional, but good for clean state)
        # db.session.query(TelegramOutbox).filter_by(chat_id=chat_id).delete()
        # db.session.commit()

        print(f"--- Starting Parallel Test for: {msg_text} ---")

        def send_msg(idx):
            with app.app_context():
                print(f"Thread {idx} starting enqueue...")
                result = TelegramService.enqueue_outbox_message(
                    chat_id=chat_id,
                    recipient_name="Tester",
                    message_type="test",
                    message_text=msg_text,
                    idempotency_key=f"key_{time.time()}_{idx}", # Unique key per thread? Yes technically different requests
                )
                print(f"Thread {idx} result: {result}")

        threads = []
        for i in range(3):
            t = threading.Thread(target=send_msg, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

        # Check results
        count_outbox = db.session.query(TelegramOutbox).filter_by(message_text=msg_text).count()
        print(f"--- Results ---")
        print(f"Total in Outbox: {count_outbox}")
        if count_outbox > 1:
            print("FAILURE: Duplicates found in outbox!")
        else:
            print("SUCCESS: Only one message in outbox.")

if __name__ == "__main__":
    test_dedupe()
