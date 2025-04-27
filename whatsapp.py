import requests
import logging
import os # Keep os import for now, might be useful later or for phone_number_id initially

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Consider moving this URL construction logic inside the class or making it more dynamic if needed
META_GRAPH_API_URL = "https://graph.facebook.com/v20.0/" # Use a recent version

class WhatsAppClient:
    """
    A client for interacting with the WhatsApp Business API (Cloud API).
    Handles sending text messages.
    """
    def __init__(self, access_token: str, phone_number_id: str):
        """
        Initializes the WhatsAppClient.

        Args:
            access_token: The specific access token (e.g., Business Token) for API calls.
            phone_number_id: The WhatsApp Business Account phone number ID to send messages from.
        """
        if not access_token:
            raise ValueError("Access token cannot be empty.")
        if not phone_number_id:
            raise ValueError("Phone number ID cannot be empty.")

        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.base_url = f"{META_GRAPH_API_URL}{self.phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        logger.info(f"WhatsAppClient initialized for phone number ID: {self.phone_number_id}") # Avoid logging token

    def send_text_message(self, to: str, message_body: str):
        """
        Sends a text message to a WhatsApp user.

        Args:
            to: The recipient's phone number (with country code, no '+').
            message_body: The content of the text message.

        Returns:
            bool: True if the message was sent successfully (API accepted it), False otherwise.
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": message_body},
        }
        logger.info(f"Attempting to send message to {to} via number ID {self.phone_number_id}")
        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            response_data = response.json()
            message_id = response_data.get("messages", [{}])[0].get("id")
            if message_id:
                logger.info(f"Message sent successfully to {to}. Message ID: {message_id}")
                return True
            else:
                logger.warning(f"Message sending API call succeeded but no message ID found in response for {to}. Response: {response_data}")
                return False # Or potentially True depending on desired handling

        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending WhatsApp message to {to}: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while sending message to {to}: {e}")
            return False

# Example usage (for testing purposes, remove or comment out in production)
# if __name__ == "__main__":
#     # Load environment variables for testing (replace with actual token/ID source in production)
#     from dotenv import load_dotenv
#     load_dotenv()
#     test_token = os.getenv("META_WA_ACCESS_TOKEN")
#     test_phone_id = os.getenv("META_WA_PHONE_NUM_ID")
#     test_recipient = os.getenv("TEST_RECIPIENT_WA_ID") # A phone number to send test messages to

#     if not all([test_token, test_phone_id, test_recipient]):
#         print("Error: Ensure META_WA_ACCESS_TOKEN, META_WA_PHONE_NUM_ID, and TEST_RECIPIENT_WA_ID are set in your .env file for testing.")
#     else:
#         client = WhatsAppClient(access_token=test_token, phone_number_id=test_phone_id)
#         success = client.send_text_message(to=test_recipient, message_body="Hello from WhatsAppClient!")
#         print(f"Test message send attempt successful: {success}") 