import os
import requests
import logging
import uuid
import mimetypes # Import mimetypes

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MEDIA_UPLOAD_DIR = "media_uploads"

class WhatsAppClient:
    """Client primarily for downloading media from the Meta WhatsApp Cloud API."""

    def __init__(self, bearer_token: str, api_version: str = "v19.0"):
        """
        Initializes the client for media download.

        Args:
            bearer_token: Meta WhatsApp Access Token.
            api_version: Graph API version (defaults to v19.0).
        """
        self.bearer_token = bearer_token
        self.base_url = f"https://graph.facebook.com/{api_version}"
        self.headers = {
            "Authorization": f"Bearer {self.bearer_token}",
        }
        # Ensure media upload directory exists
        os.makedirs(MEDIA_UPLOAD_DIR, exist_ok=True)
        logger.info(f"WhatsAppClient initialized for media operations.")
        logger.info(f"Media will be saved to: {os.path.abspath(MEDIA_UPLOAD_DIR)}")

    def get_media_url(self, media_id: str) -> str | None:
        """
        Retrieves the temporary download URL for a given media ID.

        Args:
            media_id: The ID of the media object.

        Returns:
            The temporary download URL string, or None if an error occurs.
        """
        url = f"{self.base_url}/{media_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            media_info = response.json()
            media_url = media_info.get("url")
            if not media_url:
                 logger.error(f"Could not find 'url' in response for media ID {media_id}: {media_info}")
                 return None
            logger.info(f"Retrieved media URL for ID {media_id}")
            return media_url
        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving media URL for ID {media_id}: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred retrieving media URL: {e}")
            return None

    def download_media(self, media_url: str, save_path: str) -> bool:
        """
        Downloads media content from a URL and saves it to a file.

        Args:
            media_url: The URL to download the media from.
            save_path: The full local file path to save the media.

        Returns:
            True if download and save were successful, False otherwise.
        """
        try:
            with requests.get(media_url, headers=self.headers, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            logger.info(f"Successfully downloaded media to: {save_path}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading media from {media_url}: {e}")
            if e.response is not None:
                logger.error(f"Response status code: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            # Clean up potentially partially downloaded file
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                    logger.info(f"Removed partially downloaded file: {save_path}")
                except OSError as remove_err:
                    logger.error(f"Error removing partially downloaded file {save_path}: {remove_err}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred downloading media: {e}")
             # Clean up potentially partially downloaded file
            if os.path.exists(save_path):
                 try:
                     os.remove(save_path)
                     logger.info(f"Removed partially downloaded file: {save_path}")
                 except OSError as remove_err:
                     logger.error(f"Error removing partially downloaded file {save_path}: {remove_err}")
            return False

    def download_media_by_id(
        self,
        media_id: str,
        filename_prefix: str = "media",
        save_dir: str = MEDIA_UPLOAD_DIR,
        mime_type: str | None = None,
        original_filename: str | None = None
    ) -> str | None:
        """
        Orchestrates getting the media URL and downloading the media, constructing a better filename.

        Args:
            media_id: The ID of the media to download.
            filename_prefix: A prefix to use for the saved filename (e.g., user_messageID).
            save_dir: The directory to save the file in.
            mime_type: The MIME type of the media (e.g., 'image/jpeg').
            original_filename: The original filename, if available (esp. for documents).

        Returns:
            The absolute path to the saved media file, or None if an error occurs.
        """
        logger.info(f"Attempting to download media with ID: {media_id}")
        media_url = self.get_media_url(media_id)
        if not media_url:
            return None

        # Determine file extension
        extension = ".bin" # Default fallback
        if original_filename: # Prefer extension from original filename if available
            _, ext = os.path.splitext(original_filename)
            if ext:
                extension = ext.lower()
                logger.info(f"Using extension '{extension}' from original filename: {original_filename}")
        elif mime_type: # Otherwise, try to guess from MIME type
            guessed_extension = mimetypes.guess_extension(mime_type)
            if guessed_extension:
                extension = guessed_extension
                logger.info(f"Using extension '{extension}' guessed from MIME type: {mime_type}")
            else:
                 logger.warning(f"Could not guess extension for MIME type: {mime_type}. Using default '{extension}'.")
        else:
             logger.warning("No original filename or MIME type provided. Using default extension '.bin'.")

        # Construct filename
        # Use prefix, media_id, and a unique ID to avoid collisions
        filename = f"{filename_prefix}_{uuid.uuid4()}{extension}"
        save_path = os.path.join(save_dir, filename)

        if self.download_media(media_url, save_path):
            return os.path.abspath(save_path)
        else:
            return None

# Example Usage (Updated for testing download only)
if __name__ == '__main__':
    test_access_token = os.getenv("META_WA_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
    
    if "YOUR" in test_access_token:
         print("Please set environment variable: META_WA_ACCESS_TOKEN for testing.")
    else:
        client = WhatsAppClient(bearer_token=test_access_token)
        
        # --- Test Media Download (Requires a valid media ID) ---
        test_media_id = os.getenv("TEST_MEDIA_ID", None)
        test_mime_type = os.getenv("TEST_MIME_TYPE", None) # Optional: e.g., 'image/jpeg'
        test_original_filename = os.getenv("TEST_ORIGINAL_FILENAME", None) # Optional: e.g., 'invoice.pdf'

        if test_media_id:
            print(f"\nTesting media download for ID: {test_media_id}...")
            # Use the updated method signature
            downloaded_path = client.download_media_by_id(
                media_id=test_media_id, 
                filename_prefix="test_download",
                mime_type=test_mime_type,
                original_filename=test_original_filename
            )
            if downloaded_path:
                print(f"Media downloaded successfully to: {downloaded_path}")
            else:
                print("Failed to download media.")
        else:
            print("\nSkipping media download test. Set TEST_MEDIA_ID environment variable with a valid ID to test.") 