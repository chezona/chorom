from fastapi import FastAPI, Request, HTTPException
import uvicorn
import json
import os
from typing import TypedDict, List, Dict, Any, Optional
import operator
import uuid
import hashlib
import hmac
import logging # Add logging import
import time # Add time import for sleep

# Configure logging *before* first use
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Environment Variables ---
from dotenv import load_dotenv
# Try overriding existing env vars if found in .env
load_dotenv(override=True)

META_WA_ACCESS_TOKEN = os.getenv("META_WA_ACCESS_TOKEN")
META_WA_PHONE_NUMBER_ID = os.getenv("META_WA_PHONE_NUMBER_ID")
META_WA_VERIFY_TOKEN = os.getenv("META_WA_VERIFY_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
META_APP_SECRET = os.getenv("META_APP_SECRET")

# --- Debug Print for API Key ---
logger.info(f"Loaded OpenAI Key: {OPENAI_API_KEY[:5]}..." if OPENAI_API_KEY else "OpenAI Key not found!")
# -------------------------------

# --- Manual .env Read Debug --- # Added
try:
    with open(".env", "r") as f:
        logger.debug("Manually read .env content snippet:") # Use debug level
        lines = [next(f) for _ in range(5)]
        for i, line in enumerate(lines):
            logger.debug(f"  .env Line {i+1}: {line.strip()[:50]}...")
except FileNotFoundError:
    logger.warning(".env file not found at expected location.") # Use warning
except StopIteration: # Handles files with < 5 lines
    logger.debug("Read all lines from short .env file.")
except Exception as e:
    logger.error(f"Error reading .env file: {e}") # Use error
# ---------------------------- #

# Basic validation for essential vars
if not META_WA_ACCESS_TOKEN or not META_WA_PHONE_NUMBER_ID:
    logger.error("WhatsApp environment variables missing.") # Use logger
    # exit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable missing.") # Use logger
    # exit(1)
if not META_WA_VERIFY_TOKEN:
    logger.warning("META_WA_VERIFY_TOKEN environment variable missing. pywa webhook setup needs this.") # Use logger
if not META_APP_SECRET:
     logger.warning("META_APP_SECRET environment variable missing. pywa signature verification needs this.") # Use logger

# --- WhatsApp Client Setup (Using pywa) ---
# Remove the old client import and instantiation
from whatsapp import WhatsAppClient # Keep for media download for now

app = FastAPI() # pywa needs the FastAPI app instance

# Instantiate pywa WhatsApp client
# It automatically handles webhook verification and signature checks if verify_token and app_secret are provided
wa = WhatsApp(
    phone_id=META_WA_PHONE_NUMBER_ID,
    token=META_WA_ACCESS_TOKEN,
    server=app, # Pass the FastAPI app instance
    verify_token=META_WA_VERIFY_TOKEN,
    app_secret=META_APP_SECRET, # Provide the app secret for signature validation
    callback_url=None, # Set via ngrok/deployment, pywa doesn't need it here if FastAPI handles routing
    business_account_id=None # Optional: Add if needed later
)

# --- LLM Client Setup (Standard OpenAI) ---
from langchain_openai import ChatOpenAI
# Use Pydantic v2+ directly as recommended by LangChain
from pydantic import BaseModel, Field # Updated import

llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_key=OPENAI_API_KEY,
    temperature=0
)

# Updated Pydantic model for analysis (inherits from Pydantic v2 BaseModel)
class QueryAnalysis(BaseModel):
    """Structure to hold the analysis of the user query/message."""
    intent: str = Field(description="Classify the user's primary intent. Options: 'query_product', 'ingest_product', 'greeting', 'unknown'.")
    item_name: Optional[str] = Field(default=None, description="The specific product or item name mentioned.")
    location: Optional[str] = Field(default=None, description="Any location mentioned (e.g., city, region). Applicable mostly to queries.")
    price: Optional[float] = Field(default=None, description="The price mentioned, if any (as a number). Applicable mostly to ingestions.")
    currency: Optional[str] = Field(default=None, description="The currency code (e.g., UGX, USD) mentioned, if any.")
    # Add more fields as needed, e.g., description, quantity

# --- LangGraph & Meilisearch Setup ---
from langgraph.graph import StateGraph, END
import meilisearch
import re # Import regex for price extraction

# 1. Define the State (Updated for Ingestion)
class AgentState(TypedDict):
    sender_id: str | None
    incoming_message_type: str | None # 'text', 'image', 'video', 'audio', 'document'
    incoming_text: str | None # Text body or caption
    incoming_media_id: str | None # Use for any media type
    incoming_media_mime_type: str | None # Added: e.g., 'image/jpeg'
    incoming_media_filename: str | None # Added: For documents
    incoming_media_path: str | None # Local path to downloaded media
    
    # Analysis results
    intent: str | None
    item_name: str | None
    location: str | None
    price: float | None
    currency: str | None
    description: str | None # Added for ingestion
    product_to_ingest: Optional[Dict[str, Any]] # Added: Data structured for ingestion
    
    # Meilisearch related
    meili_filters: str | None
    search_results: List[Dict[str, Any]] | None
    
    # Final output
    response: str | None
    meili_task_id: str | None # Added to track Meilisearch task
    meili_task_status: str | None # Added: 'enqueued', 'processing', 'succeeded', 'failed'
    whatsapp_message_object: pt.Message | None # Store the pywa message object

# 2. Meilisearch Client
# Ensure Meilisearch container is running (docker run ...)
meili_client = meilisearch.Client('http://localhost:7700')
meili_index = meili_client.index('products')

# 3. Define Nodes
def analyze_intent_node(state: AgentState):
    """Analyzes message text/media using LLM to extract intent and key entities."""
    logger.info("--- Running Analyze Intent Node ---")
    text_content = state.get('incoming_text') # Can be None
    message_type = state.get('incoming_message_type')
    media_path = state.get('incoming_media_path') # Get media path
    media_id = state.get('incoming_media_id') # Check if media ID exists

    # --- Handle No Content --- # Updated Check
    # If there's no text AND no media ID (meaning no media was sent or couldn't be processed)
    if not text_content and not media_id:
        logger.warning("Analyze Intent: No text content or media ID found.")
        state['intent'] = 'error'
        state['response'] = "Sorry, I couldn't understand the message content. Please send text or media."
        return state
    
    # --- Determine Intent (Prioritize Media for Ingestion) --- # Updated Logic
    # Use media_id to check for media presence
    if media_id:
        logger.info(f"Media detected (type: {message_type}, id: {media_id}), setting intent to 'ingest_product'.")
        state['intent'] = 'ingest_product'
        if not text_content:
             text_content = "" # Use empty string for LLM if no caption
             logger.info("Media present but no text caption found.")
    elif text_content:
        logger.info("Only text detected, using LLM for intent and entity extraction.")
        # LLM analysis will determine the intent
        pass
    else:
        logger.error("Analyze Intent: Reached unexpected state (no text, no media ID).")
        state['intent'] = 'error'
        state['response'] = "Internal error processing message state."
        return state

    # --- LLM Analysis (if text is available or forced intent needs details) ---
    try:
        structured_llm = llm.with_structured_output(QueryAnalysis)
        prompt_guidance = (
            "The intent is likely either 'query_product' (asking about something) or 'ingest_product' (stating availability/price/details of something, possibly to sell). "
            f"A media file ({message_type}) was {'present (ID: ' + media_id + ')' if media_id else 'not present'}. "
            f"If media was present, the intent is almost certainly 'ingest_product'. "
            "Extract item name, price (if stated), and currency (if stated) from the text. The full text can serve as a description if the intent is ingestion. "
            "If media was not present, determine intent primarily from the text (lean towards 'query_product' unless keywords like 'sell', 'stock', 'available', 'price' suggest ingestion). Extract location only if it's a query." 
        )
        prompt = (
            f"Analyze the following user message content. {prompt_guidance}"
            f"Text Content: '{text_content}'"
        )
        analysis: QueryAnalysis = structured_llm.invoke(prompt)
        logger.info(f"LLM Analysis Result: {analysis}")

        # Override LLM intent if media was present
        if media_id:
            state['intent'] = 'ingest_product'
            logger.info("Ensuring intent is 'ingest_product' due to media presence.")
        else:
            state['intent'] = analysis.intent
            logger.info(f"Setting intent based on LLM analysis (no media): {analysis.intent}")

        # Store extracted entities
        state['item_name'] = analysis.item_name
        state['price'] = analysis.price
        state['currency'] = analysis.currency
        # Only store location if it was likely a query and no media was sent
        state['location'] = analysis.location if state['intent'] == 'query_product' and not media_id else None
        # Use text content as description if ingesting
        state['description'] = text_content if state['intent'] == 'ingest_product' else None

        # Construct Meilisearch filter only for queries
        if state['intent'] == 'query_product' and state['location']:
            state['meili_filters'] = f"vendor = '{state['location']}'" # Assuming location filter refers to vendor
            logger.info(f"Set Meilisearch filter: {state['meili_filters']}")
        else:
            state['meili_filters'] = None

        # Set initial response for non-actionable intents
        if state['intent'] == 'greeting':
            state['response'] = "Hello there! How can I help you?"
        elif state['intent'] == 'unknown':
            state['response'] = "Sorry, I'm not sure how to help with that. I can search for products or add new ones if you provide details."

    except Exception as e:
        logger.exception(f"Error during LLM analysis: {e}")
        state['intent'] = 'error'
        state['response'] = "Sorry, I had trouble analyzing the details of your request."

    logger.info(f"Analyze Intent Node Completed. Intent: '{state['intent']}', Item: '{state['item_name']}'")
    return state

def structure_ingestion_data_node(state: AgentState):
    """Prepares structured data for adding to Meilisearch, including media path."""
    logger.info("--- Running Structure Ingestion Data Node --- ")
    
    # Retrieve data from state
    sender_id = state.get('sender_id')
    item_name = state.get('item_name')
    description = state.get('description')
    price = state.get('price')
    currency = state.get('currency', "UGX") # Default currency
    media_path = state.get('incoming_media_path') # Get the media path

    # Basic validation
    if not item_name and not description:
        logger.warning("Cannot structure ingestion data: Missing item name and description.")
        # Set an error response, though this node ideally shouldn't be reached if intent analysis was poor.
        state['response'] = "Missing product name/description for ingestion."
        state['product_to_ingest'] = None # Ensure no data proceeds
        return state # Or should we allow routing to END? Let's stop data flow here.

    # Use description as name if item_name wasn't extracted but description exists
    if not item_name and description:
        item_name = description.split('\n')[0][:50] # Use first line of description as fallback name
        logger.info(f"Using description start as fallback item name: '{item_name}'")
    elif not item_name:
        item_name = "Unknown Item" # Final fallback
        logger.warning("Using 'Unknown Item' as item name.")

    # Prepare the dictionary for Meilisearch
    product_data = {
        "id": str(uuid.uuid4()), # Generate unique ID
        "name": item_name,
        "description": description or "", # Ensure description is at least an empty string
        "price": price, # Can be None if not provided
        "currency": currency,
        "category": "Unknown", # TODO: Can LLM extract category too?
        "vendor": sender_id, # Use sender_id as vendor for now
        "media_path": media_path # Store the path to the downloaded media
    }
    
    # Clean None values for Meilisearch? (Optional, Meili usually handles nulls)
    # product_data = {k: v for k, v in product_data.items() if v is not None}

    logger.info(f"Structured product data for Meilisearch: {product_data}")
    state['product_to_ingest'] = product_data # Add to state for next node
    return state

def add_product_to_meili_node(state: AgentState):
    """Adds the structured product data to Meilisearch and initiates polling."""
    logger.info("--- Running Add Product to Meili Node ---")
    product_data = state.get('product_to_ingest')
    product_name = product_data.get('name', 'the product') if product_data else 'the product' # Get name for messages

    if not product_data:
        logger.error("No product data found in state to add to Meilisearch.")
        state['response'] = "Error: Could not structure product data for storage."
        # Consider setting intent to 'error' or deciding how to handle this
        return state

    try:
        logger.info(f"Adding document to Meilisearch index 'products': {product_data['id']}")
        task_info = meili_index.add_documents([product_data])
        logger.info(f"Meilisearch add_documents task info: {task_info}")

        # Check if task_info is the new TaskInfo object or legacy dict
        if hasattr(task_info, 'task_uid'):
            task_id = task_info.task_uid
        elif isinstance(task_info, dict) and 'taskUid' in task_info:
             task_id = task_info['taskUid']
        else:
            logger.error(f"Could not extract task ID from Meilisearch response: {task_info}")
            state['response'] = "Error: Failed to get task ID after submitting product."
            return state

        state['meili_task_id'] = task_id
        state['meili_task_status'] = 'enqueued' # Initial status
        logger.info(f"Meilisearch Task ID {task_id} enqueued for product {product_data['id']}.")
        # No immediate response here, polling node will handle confirmation

    except Exception as e:
        logger.exception(f"Error adding document to Meilisearch: {e}")
        state['response'] = "Sorry, there was an error adding the product to the catalog."
        # Optionally set intent to 'error'

    return state

def search_meilisearch_node(state: AgentState):
    """Searches Meilisearch using extracted item name and filters."""
    logger.info("--- Running Search Meilisearch Node ---") # Use logger
    query = state.get('item_name') # Use extracted item name
    filters = state.get('meili_filters')

    # This node should only run if the intent requires search
    # The check for query/error is still a good safeguard
    if not query or state.get('intent') == 'error':
        if not state.get('response'):
            state['response'] = "Sorry, I couldn't determine what to search for."
        state['search_results'] = []
        return state

    try:
        search_params = {
            "filter": filters
        } if filters else {}

        logger.info(f"Searching index 'products' for: '{query}' with filters: {filters}") # Use logger
        search_result = meili_index.search(query, search_params)
        hits = search_result.get('hits', [])
        state['search_results'] = hits
        logger.info(f"Found {len(hits)} results.") # Use logger

        if not hits:
             state['response'] = f"I couldn't find any '{query}'" + (f" in {state['location']}." if state['location'] else ".")
        else:
             # Basic formatting, improve later
             formatted_hits = "\n".join([
                 f"- {hit.get('name', 'N/A')} ({hit.get('price', 0)} {hit.get('currency', '')}, Vendor: {hit.get('vendor', 'N/A')})"
                 for hit in hits[:3] # Limit to top 3 for brevity
             ])
             location_str = f" in {state['location']}" if state['location'] else ""
             state['response'] = f"Found these results for '{query}'{location_str}:\n{formatted_hits}"

    except Exception as e:
        logger.error(f"Error searching Meilisearch: {e}") # Use logger
        state['search_results'] = []
        state['response'] = "Sorry, there was an error searching."
    return state

# 4. Define Conditional Edge Function (Updated)
def route_after_intent_analysis(state: AgentState):
    """Routes workflow based on classified intent."""
    logger.info("--- Routing based on Intent --- ") # Use logger
    intent = state.get('intent')
    logger.info(f"Routing with intent: {intent}") # Use logger

    query_intents = ['query_product'] # Add 'ask_price', 'check_location' if LLM distinguishes them
    ingest_intents = ['ingest_product']

    if intent in query_intents:
        # Check if we actually have something to search for
        if state.get('item_name'):
            logger.info("Decision: Proceed to search_meili") # Use logger
            return "search_meili"
        else:
            logger.info("Decision: Query intent, but no item found. Ending.") # Use logger
            if not state.get('response'):
                state['response'] = "You asked to search, but didn't specify an item."
            return END
    elif intent in ingest_intents:
         logger.info("Decision: Proceed to structure_ingestion_data") # Use logger
         return "structure_ingestion_data"
    elif intent == 'greeting':
        logger.info("Decision: Intent is greeting. Ending.") # Use logger
        return END
    elif intent == 'unknown':
         logger.info("Decision: Intent is unknown. Ending.") # Use logger
         return END
    else: # Includes 'error' etc.
        logger.info("Decision: Intent is error or unexpected. Ending.") # Use logger
        if not state.get('response'):
             state['response'] = "Sorry, I encountered an issue processing your request."
        return END

# 5. Build the Graph (Updated with ingestion path)
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("analyze_intent", analyze_intent_node)
workflow.add_node("search_meili", search_meilisearch_node)
workflow.add_node("structure_ingestion_data", structure_ingestion_data_node)
workflow.add_node("add_product_to_meili", add_product_to_meili_node)

# Define edges
workflow.set_entry_point("analyze_intent")

# Conditional routing after intent analysis
workflow.add_conditional_edges(
    "analyze_intent",
    route_after_intent_analysis,
    {
        "search_meili": "search_meili",
        "structure_ingestion_data": "structure_ingestion_data",
        END: END
    }
)

# Edges for the query path
workflow.add_edge("search_meili", END)

# Edges for the ingestion path
workflow.add_edge("structure_ingestion_data", "add_product_to_meili")
workflow.add_edge("add_product_to_meili", END)

# Compile the graph
app_graph = workflow.compile()

# --- FastAPI Application ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Service is running", "pywa_status": "initialized"}

# --- pywa Handlers --- #

# Directory to store downloaded media
MEDIA_UPLOAD_DIR = "media_uploads"
if not os.path.exists(MEDIA_UPLOAD_DIR):
    os.makedirs(MEDIA_UPLOAD_DIR)

# Create instance of our existing WhatsAppClient for media downloads
# (Could potentially be replaced by pywa's download methods if preferred)
media_downloader = WhatsAppClient(bearer_token=META_WA_ACCESS_TOKEN)

@wa.on_message() # Handles text, media (image, video, audio, document) messages
async def handle_incoming_message(client: WhatsApp, msg: pt.Message):
    """Handles incoming WhatsApp messages (text, media with captions)."""
    logger.info(f"Received message via pywa: Type={msg.type.value}, From={msg.from_user.wa_id}, Name={msg.from_user.name}, Body={msg.text}, Media={msg.media}")

    initial_state = AgentState(
        sender_id=msg.from_user.wa_id,
        incoming_message_type=msg.type.value, # e.g., 'text', 'image'
        incoming_text=None,
        incoming_media_id=None,
        incoming_media_path=None,
        incoming_media_mime_type=None,
        incoming_media_filename=None,
        intent=None,
        item_name=None,
        location=None,
        price=None,
        currency=None,
        description=None,
        product_to_ingest=None,
        meili_filters=None,
        search_results=None,
        response=None,
        meili_task_id=None,
        meili_task_status=None,
        whatsapp_message_object=msg # Store the message object
    )

    # Extract text (body or caption)
    if msg.text:
        initial_state['incoming_text'] = msg.text
        logger.info(f"Extracted text: {msg.text}")
    elif msg.caption:
        initial_state['incoming_text'] = msg.caption
        logger.info(f"Extracted caption: {msg.caption}")

    # Handle media
    media_to_download: Optional[pt.MediaBase] = None
    if msg.image:
        media_to_download = msg.image
        initial_state['incoming_media_mime_type'] = msg.image.mime_type
    elif msg.video:
        media_to_download = msg.video
        initial_state['incoming_media_mime_type'] = msg.video.mime_type
    elif msg.audio:
        media_to_download = msg.audio
        initial_state['incoming_media_mime_type'] = msg.audio.mime_type
    elif msg.document:
        media_to_download = msg.document
        initial_state['incoming_media_mime_type'] = msg.document.mime_type
        initial_state['incoming_media_filename'] = msg.document.filename

    if media_to_download:
        media_id = media_to_download.media_id
        initial_state['incoming_media_id'] = media_id
        logger.info(f"Media detected: ID={media_id}, Type={initial_state['incoming_message_type']}, Mime={initial_state['incoming_media_mime_type']}")
        
        # --- Download Media --- #
        try:
            # Use our existing download logic (or switch to pywa's if available/preferred)
            # file_path = await media_to_download.download(path=MEDIA_UPLOAD_DIR) # Check if pywa has async download
            
            # Using existing client for download
            file_path = media_downloader.download_media(
                media_id=media_id,
                filename_prefix=f"{msg.from_user.wa_id}_{msg.id}", # Unique prefix
                save_dir=MEDIA_UPLOAD_DIR,
                mime_type=initial_state['incoming_media_mime_type'], # Pass mime type
                original_filename=initial_state['incoming_media_filename'] # Pass original filename for docs
            )
            
            if file_path:
                initial_state['incoming_media_path'] = file_path
                logger.info(f"Media downloaded successfully to: {file_path}")
            else:
                logger.error(f"Failed to download media for ID: {media_id}")
                # Optionally send an immediate error reply?
                # await msg.reply_text("Sorry, I couldn't download the media you sent.") 
                # Or let the graph handle it based on missing media_path

        except Exception as e:
            logger.exception(f"Error downloading media ID {media_id}: {e}")
            # Proceed without media path, graph should handle it

    # --- Invoke LangGraph Workflow --- #
    try:
        logger.info(f"Invoking LangGraph for sender {initial_state['sender_id']}")
        # The graph runs synchronously within this async handler for now
        # Consider running graph in executor if it becomes blocking
        # For pywa_async, graph execution should ideally be async
        # Check LangGraph docs for async invocation
        final_state = app_graph.invoke(initial_state)
        logger.info(f"LangGraph execution finished. Final state response: {final_state.get('response')}")
        # Reply is now handled within the graph's send_whatsapp_confirmation_node

    except Exception as e:
        logger.exception(f"Error during LangGraph execution for sender {initial_state['sender_id']}: {e}")
        # Send a fallback error message if graph fails completely
        try:
            await msg.reply_text(text="Sorry, an internal error occurred while processing your request.")
        except Exception as reply_err:
            logger.exception(f"Failed to send fallback error reply: {reply_err}")

# To run the app:
# python -m uvicorn main:app --reload --port 8000
if __name__ == "__main__":
    # Ensure Meilisearch is running before starting!
    uvicorn.run(app, host="0.0.0.0", port=8000) 