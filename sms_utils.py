from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from config import TWILIO_SID, TWILIO_AUTH, TWILIO_PHONE

TWILIO_AUTH_OK = False
twilio_client = None

def init_twilio():
    global twilio_client, TWILIO_AUTH_OK
    try:
        twilio_client = Client(TWILIO_SID, TWILIO_AUTH)
        twilio_client.api.accounts(TWILIO_SID).fetch()
        TWILIO_AUTH_OK = True
        print("[OK] Twilio authentication successful")
    except TwilioRestException as e:
        print(f"[ERROR] Twilio authentication failed: {e}")
        TWILIO_AUTH_OK = False

def send_warning_sms(cell, probability, numbers):
    if not TWILIO_AUTH_OK or not twilio_client:
        print(f"[WARN] Cannot send SMS to {cell}: Twilio auth failed")
        return

    message_text = f"""
⚠ Temperature Alert
Location: {cell}
Probability: {round(probability*100,2)}%
High temperature detected.
Please check immediately.
"""
    for number in numbers:
        try:
            message = twilio_client.messages.create(
                body=message_text,
                from_=TWILIO_PHONE,
                to=number
            )
            print(f"[OK] SMS sent to {number}, SID: {message.sid}")
        except TwilioRestException as e:
            print(f"[ERROR] Failed to send SMS to {number}: {e}")

def send_custom_sms(number, message_text):
    if not TWILIO_AUTH_OK or not twilio_client:
        print(f"[WARN] Cannot send SMS to {number}: Twilio auth failed")
        return False
    try:
        message = twilio_client.messages.create(
            body=message_text,
            from_=TWILIO_PHONE,
            to=number
        )
        print(f"[OK] SMS sent to {number}, SID: {message.sid}")
        return True
    except TwilioRestException as e:
        print(f"[ERROR] Failed to send SMS to {number}: {e}")
        return False
