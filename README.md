# Meilisearch Multimodal Shopping Chatbot

## Goal

This project aims to create an intelligent, multimodal chatbot application for shopping. Customers will interact with the bot via a dedicated interface (web/mobile) using text, audio, or video to search for products. Product data is primarily ingested into the underlying Meilisearch catalog by **sellers sending messages (text, images, videos) directly to the bot via WhatsApp**.
The system will also support augmenting the product catalog via web scraping.

## Architecture

The system is composed of the following components:

1.  **FastAPI Backend (`main.py`):**
    *   The core web server using FastAPI.
    *   Initializes and integrates with the **`pywa` library** to handle WhatsApp interactions.
    *   Defines **`pywa` message handlers** to receive seller product ingestion messages.
    *   Handles API requests from the **customer-facing chat application** (future).
    *   Orchestrates the processing logic using **LangGraph**.
    *   Provides search results and interaction logic for the customer chat app.
2.  **`pywa` (Python WhatsApp Wrapper - `main.py`):**
    *   Handles incoming **webhook requests from Meta WhatsApp Cloud API** for seller product ingestion.
    *   Automatically verifies **webhook subscriptions** and **message signatures** using configured tokens/secrets.
    *   Parses incoming messages (text, media, captions) into convenient Python objects (`pywa.types`).
    *   Provides the `WhatsApp` client object used by LangGraph nodes to send replies back to sellers.
    *   Routes incoming messages to the appropriate handler functions based on type/filters.
3.  **Meta WhatsApp Cloud API:**
    *   Connects **seller WhatsApp messages** to our FastAPI backend via webhooks managed by `pywa`.
4.  **LangGraph Workflow (`main.py`):**
    *   Manages the state for each incoming message/request.
    *   Defines a graph of nodes (processing steps) and edges (transitions).
    *   **Key Nodes for Seller Ingestion:**
        *   `analyze_intent_node`: Uses an LLM (OpenAI) to analyze text/media presence (passed from `pywa` handler), determine intent (primarily `ingest_product` for sellers), and extract key details.
        *   `structure_ingestion_data_node`: Prepares a structured JSON document for the new product, including the path to locally stored media.
        *   `add_product_to_meili_node`: Adds the structured product data to Meilisearch and gets the task ID.
        *   `poll_meili_task_status_node`: Polls Meilisearch for the task completion status.
        *   `send_whatsapp_confirmation_node`: Uses the `pywa` client (via the message object stored in state) to send a confirmation/reply back to the seller via the WhatsApp API.
    *   **Future Nodes for Customer Interaction:** Search, multimodal processing, etc.
5.  **OpenAI API (`main.py`):**
    *   The Large Language Model (LLM) used for Natural Language Understanding (NLU) and generation.
    *   Structured output is used for reliable data extraction.
    *   (Future) Speech-to-Text (e.g., Whisper) for audio input.
6.  **Meilisearch (`main.py`):**
    *   The search engine storing the product catalog.
    *   Accessed via the `meilisearch-python` client.
    *   Contains a `products` index with fields for name, description, price, vendor, category, and `media_path`.
7.  **WhatsApp Media Downloader (`whatsapp_client.py`):** # Renamed/Refocused
    *   Handles interactions with the Meta Graph API specifically for:
        *   Retrieving media URLs using media IDs (obtained from `pywa` message objects).
        *   Downloading media sent by sellers and saving it locally.
8.  **Media Storage (`media_uploads/` directory):**
    *   Currently stores downloaded media files locally. (Future: Could be cloud storage like S3).
9.  **Customer Chat Frontend (Future):**
    *   Web or mobile application interface for customer interactions.
10. **Web Scraping Engine (Future):**
    *   Component to scrape product data from external websites.
11. **Environment Variables (`.env`):**
    *   Stores sensitive credentials and configuration for FastAPI, `pywa`, OpenAI, and Meilisearch.

## Current Status (Phase 1 Complete - Revised)

*   **Robust Seller Ingestion via WhatsApp (using `pywa`):**
    *   FastAPI server integrates `pywa` to handle the `/whatsapp` webhook.
    *   `pywa` automatically handles webhook signature verification and subscription checks.
    *   `pywa` handlers parse incoming text messages and common media types (image, video, audio, document), extracting details like captions, filenames, and media IDs.
    *   Media is downloaded using the media ID (obtained via `pywa`) by the `whatsapp_client.py` utility and saved locally to `media_uploads/`.
    *   LangGraph workflow reliably processes seller messages triggered by `pywa` handlers:
        *   Intent analysis prioritizes `ingest_product` if media is present.
        *   LLM extracts details (name, price, currency) from text/caption.
        *   Data is structured, including the local `media_path`.
        *   Product data is added to the `products` index in Meilisearch.
        *   Meilisearch task status polling confirms successful ingestion.
        *   Confirmation reply sent back to the seller via `pywa`.
*   Basic Meilisearch client setup.
*   OpenAI (GPT-4o-mini) integration for NLU.
*   `whatsapp_client.py` focused on media downloading.
*   Basic logging implemented.

## To-Do / Future Enhancements (Revised)

**Phase 2: Basic Customer Shopping App**
*   Build initial **web application frontend** with text-based chat interface.
*   Create backend API endpoints in FastAPI to serve the frontend.
*   Implement customer-facing LangGraph workflow for **product search** (leveraging `search_meilisearch_node`).
*   Connect frontend to backend for text-based product queries.
*   Display search results (including potentially linking to stored media) in the chat interface.

**Phase 3: Multimodal Customer Input & Refinements**
*   Integrate **Speech-to-Text** (e.g., OpenAI Whisper) for audio queries from the customer app.
*   Define and implement handling for customer **video input** (e.g., store links/thumbnails).
*   **Refine LLM Prompts:** Improve accuracy for both seller ingestion details (category, better name extraction) and customer query understanding.
*   **Refine Meilisearch Settings:** Optimize `searchableAttributes`, `filterableAttributes`, `rankingRules` for customer queries.
*   **Media URL Serving:** Instead of just storing local paths, implement a way to serve media files (e.g., via a FastAPI endpoint or by moving to cloud storage with public URLs) so they can be displayed in the customer app.

**Phase 4: Web Scraping & Advanced Features**
*   Develop and deploy the **web scraping** component.
*   Investigate/implement more advanced features (recommendations, comparisons).
*   Explore handling **WhatsApp Group Scraping** (with caution regarding feasibility/ToS).

**Ongoing / Foundational:**
*   **Containerization:** Create `Dockerfile` and `docker-compose.yml` for easier setup and deployment.
*   **Testing:** Add comprehensive unit and integration tests.
*   **Error Handling:** Enhance resilience, rate limit handling, etc.
*   **Security:** Revisit webhook security, consider authentication for customer app.
*   **Configuration:** Make paths, models, etc., more configurable.

## Milestones (Revised)

1.  **Seller Ingestion Foundation (Complete):**
    *   Robust WhatsApp message/media handling for sellers.
    *   Reliable data structuring and Meilisearch ingestion with confirmation.
2.  **Basic Customer Search App:**
    *   Functional text-based chat frontend for customer queries.
    *   Backend API and search workflow connected.
3.  **Multimodal Customer Input:**
    *   Customers can query using voice (Speech-to-Text).
    *   Basic handling of video input.
    *   Media display in chat.
4.  **Data Augmentation & Intelligence:**
    *   Web scraping operational.
    *   Improved NLP, search relevance, potential recommendations.
5.  **Production Readiness:**
    *   Containerization, comprehensive testing, deployment strategy, monitoring.

## Technology Stack

*   **Backend:** Python, FastAPI
*   **WhatsApp Integration:** `pywa`
*   **Workflow Orchestration:** LangGraph
*   **LLM:** OpenAI (GPT-4o-mini, Whisper)
*   **Search Engine:** Meilisearch
*   **Seller Interface:** Meta WhatsApp Cloud API (via `pywa`)
*   **Customer Interface:** (Future) Web Framework (e.g., React, Vue, Svelte)
*   **Media Storage:** Local Filesystem (initially)
*   **Libraries:** `meilisearch`, `langchain-openai`, `python-dotenv`, `requests`, `uvicorn`, `langgraph`, `pywa`

## Setup Instructions

1.  **Prerequisites:**
    *   Python 3.9+
    *   Docker Desktop (or Docker Engine)
    *   Access to Meta Developer Portal to set up a WhatsApp Business App.

2.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

3.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    # Activate (Windows PowerShell)
    .\.venv\Scripts\Activate.ps1
    # Activate (Linux/macOS)
    # source .venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *   This now includes `pywa` and its FastAPI dependencies.

5.  **Set up Meilisearch:**
    *   Ensure Docker is running.
    *   Start Meilisearch using Docker (this persists data in a volume named `meili_data`):
        ```bash
        docker run -it --rm --name meilisearch -p 7700:7700 -v meili_data:/meili_data -e MEILI_ENV=development getmeili/meilisearch:latest
        ```
    *   You can access the Meilisearch web UI at `http://localhost:7700`.

6.  **Add Data to Meilisearch (Optional Initial Data):**
    *   The repository includes sample data in `products.json`.
    *   Index this data using `curl` or PowerShell:
        *   **PowerShell:**
            ```powershell
            Invoke-RestMethod -Uri 'http://localhost:7700/indexes/products/documents' `
              -Method Post `
              -ContentType 'application/json' `
              -InFile 'products.json'
            ```
        *   **curl (Linux/macOS/WSL):**
            ```bash
            curl -X POST 'http://localhost:7700/indexes/products/documents' \
              -H 'Content-Type: application/json' \
              --data-binary '@products.json'
            ```

7.  **Configure Environment Variables:**
    *   Create a file named `.env` in the project root.
    *   Add your Meta Cloud API credentials (see `.env.example` or below). **`pywa` uses `META_APP_SECRET` for signature validation.**
        ```dotenv
        META_WA_ACCESS_TOKEN=YOUR_WHATSAPP_ACCESS_TOKEN
        META_WA_PHONE_NUMBER_ID=YOUR_WHATSAPP_PHONE_NUMBER_ID
        META_WA_VERIFY_TOKEN=YOUR_CHOSEN_WEBHOOK_VERIFY_TOKEN
        META_APP_SECRET=YOUR_WHATSAPP_APP_SECRET # Important for pywa signature validation
        OPENAI_API_KEY=YOUR_OPENAI_API_KEY
        ```
    *   **Important:** Add `.env` to your `.gitignore` file if using Git.

8.  **Run the FastAPI Server:**
    ```bash
    python -m uvicorn main:app --reload --port 8000
    ```
    *   The server will run on `http://localhost:8000`.
    *   `pywa` integrates with the running FastAPI app to handle requests to the webhook path.

## Testing Seller Ingestion Locally

1.  **Get Meta Credentials:** Follow Meta Developer Portal steps to get a Test Phone Number, Access Token, Phone Number ID, App Secret, and create a Verify Token.
2.  **Update `.env`:** Fill in all the values obtained in step 1, **including `META_APP_SECRET`**.
3.  **Expose Local Server:** Use `ngrok http 8000` to get a public HTTPS URL.
4.  **Configure Meta Webhook:** In your Meta App dashboard (WhatsApp -> Configuration), under Webhooks, click "Edit". Set the Callback URL to your `ngrok` HTTPS URL (e.g., `https://<id>.ngrok.io`). **Do NOT add `/whatsapp` to the URL here** - `pywa` handles the routing from the base URL provided to FastAPI. Enter your Verify Token. Click "Verify and Save". Then, under Webhook fields, click "Manage" and subscribe to `messages`.
5.  **Start Server:** Run `python -m uvicorn main:app --reload --port 8000`.
6.  **Send Message:** Send a WhatsApp message (text or image/video with caption) from your personal phone number (added as a recipient in Meta setup) **to** the Meta Test Phone Number.
7.  **Observe:** Check the FastAPI server logs. You should see `pywa` logging the incoming message, the LangGraph execution, media download logs (from `whatsapp_client.py`), data being added to Meilisearch, task polling, and finally the confirmation reply being sent back via `pywa` to your WhatsApp.

## Testing Customer Search (Future)

(Instructions TBD once the customer frontend and search API are built)
