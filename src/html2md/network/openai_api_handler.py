"""
OpenAI API-based handler for accessing ChatGPT conversations.
This module implements OAuth authentication and API-based access to ChatGPT content.
"""

import json
import re
import requests
from datetime import datetime, timedelta
from html2md.network.chatgpt_handler import extract_conversation_id
from html2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger("openai_api_handler")

# OpenAI API endpoints
AUTH_URL = "https://auth0.openai.com/oauth/token"
SESSION_URL = "https://chat.openai.com/api/auth/session"
CONVERSATION_API_URL = "https://chat.openai.com/backend-api/conversation/{conversation_id}"
CONVERSATIONS_LIST_URL = "https://chat.openai.com/backend-api/conversations"

# In-memory token cache
token_cache = {
    "access_token": None,
    "refresh_token": None,
    "expires_at": None
}


def get_oauth_token(email, password):
    """
    Get an OAuth token using email/password authentication.
    """
    logger.info("Obtaining OAuth token via email/password authentication")
    
    # Step 1: Get CSRF token
    csrf_session = requests.Session()
    login_page_response = csrf_session.get("https://chat.openai.com/auth/login")
    
    # Extract the CSRF token from the login page
    csrf_token = None
    if login_page_response.status_code == 200:
        csrf_token_match = re.search(r'<input type="hidden" name="csrfToken" value="([^"]+)"', login_page_response.text)
        if csrf_token_match:
            csrf_token = csrf_token_match.group(1)
            logger.debug("Successfully extracted CSRF token")
        else:
            logger.warning("Could not find CSRF token in login page")
    else:
        logger.error(f"Failed to load login page: {login_page_response.status_code}")
        return None
    
    if not csrf_token:
        logger.error("CSRF token is required for authentication")
        return None
    
    # Step 2: Submit login credentials
    login_data = {
        "email": email,
        "password": password,
        "csrfToken": csrf_token
    }
    
    login_response = csrf_session.post(
        "https://chat.openai.com/api/auth/signin/email",
        data=login_data,
        headers={"Referer": "https://chat.openai.com/auth/login"}
    )
    
    if login_response.status_code != 200:
        logger.error(f"Login failed with status code: {login_response.status_code}")
        logger.debug("Login response body omitted")
        return None
    
    # Step 3: Get callback URL and complete authentication
    try:
        callback_url = login_response.json().get("url")
        if not callback_url:
            logger.error("No callback URL found in login response")
            return None
        
        logger.debug(f"Following callback URL: {callback_url}")
        callback_response = csrf_session.get(callback_url)
        
        if callback_response.status_code != 200:
            logger.error(f"Callback request failed: {callback_response.status_code}")
            return None
        
        # Step 4: Get the final session token
        session_response = csrf_session.get("https://chat.openai.com/api/auth/session")
        if session_response.status_code != 200:
            logger.error(f"Session API request failed: {session_response.status_code}")
            return None
        
        session_data = session_response.json()
        access_token = session_data.get("accessToken")
        
        if not access_token:
            logger.error("No access token found in session response")
            return None
        
        # Calculate expiration time (default to 1 hour if not specified)
        expires_in = session_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Update token cache
        token_cache["access_token"] = access_token
        token_cache["expires_at"] = expires_at
        
        logger.info("Successfully obtained OAuth access token")
        return access_token
        
    except Exception as e:
        logger.error(f"Error during OAuth authentication: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


def get_access_token_from_cookies(session_cookies):
    """
    Get an access token from the session cookies.
    """
    logger.info("Attempting to get access token from cookies")
    
    # Check if we have a session token cookie
    session_token = None
    for cookie_name, cookie_value in session_cookies.items():
        if cookie_name == "__Secure-next-auth.session-token":
            session_token = cookie_value
            logger.debug("Found session token in cookies")
            break
    
    if not session_token:
        logger.warning("No session token found in cookies")
        return None
    
    # Use the session token to get an access token
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Cookie": f"__Secure-next-auth.session-token={session_token}"
    }
    
    try:
        # Create a new session for this specific request
        request_session = requests.Session()
        response = request_session.get(SESSION_URL, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Failed to get access token from session API: {response.status_code}")
            return None
        
        data = response.json()
        access_token = data.get("accessToken")
        
        if not access_token:
            logger.error("No access token found in API response")
            return None
        
        # Calculate expiration time (default to 1 hour if not specified)
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Update token cache
        token_cache["access_token"] = access_token
        token_cache["expires_at"] = expires_at
        
        logger.info("Successfully obtained access token from cookies")
        return access_token
        
    except Exception as e:
        logger.error(f"Error getting access token from cookies: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


def get_conversation_api(conversation_id, access_token):
    """
    Get conversation data using the OpenAI API with an access token.
    """
    logger.info(f"Getting conversation {conversation_id} using API and access token")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    api_url = CONVERSATION_API_URL.format(conversation_id=conversation_id)
    
    try:
        response = requests.get(api_url, headers=headers, timeout=30)
        
        logger.debug(f"API response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"API request failed with status {response.status_code}")
            
            logger.debug("API error response body omitted")
                
            return None
        
        try:
            conversation_data = response.json()
            logger.info("Successfully retrieved conversation data via API")
            return conversation_data
        except json.JSONDecodeError:
            logger.error("Failed to parse API response as JSON")
            logger.debug("Invalid JSON response body omitted")
            return None
            
    except Exception as e:
        logger.error(f"Error accessing conversation API: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None


def generate_conversation_html(conversation_data, conversation_id):
    """
    Generate HTML from conversation data.
    """
    logger.info("Generating HTML from conversation data")
    
    html = "<!DOCTYPE html>\n<html><head><title>ChatGPT Conversation</title>"
    html += "<style>\n"
    html += ".user-message { background-color: #f0f7fb; padding: 15px; margin: 10px 0; border-radius: 5px; }\n"
    html += ".assistant-message { background-color: #f9f9f9; padding: 15px; margin: 10px 0; border-radius: 5px; }\n"
    html += ".system-message { background-color: #f5f5f5; padding: 10px; margin: 10px 0; font-style: italic; border-radius: 5px; }\n"
    html += "pre { background-color: #282c34; color: #abb2bf; padding: 10px; border-radius: 5px; overflow: auto; }\n"
    html += "code { font-family: monospace; background-color: #eee; padding: 2px 4px; border-radius: 3px; }\n"
    html += "</style>\n"
    html += "</head><body>\n"
    html += f"<h1>ChatGPT Conversation ({conversation_id})</h1>\n"
    
    try:
        if "mapping" in conversation_data:
            logger.debug(f"Found 'mapping' with {len(conversation_data['mapping'])} entries")
            # Extract messages and rebuild conversation
            messages = conversation_data.get("mapping", {})
            conversation = []
            
            # Handle different API response structures
            for msg_id, msg_data in messages.items():
                logger.debug(f"Processing message: {msg_id}")
                if "message" in msg_data and msg_data.get("message"):
                    msg = msg_data["message"]
                    author = msg.get("author", {}).get("role", "unknown")
                    content = msg.get("content", {})
                    
                    if "parts" in content and content["parts"]:
                        logger.debug(f"Found content parts for {author} message")
                        text = content["parts"][0]
                        # Convert markdown code blocks to HTML
                        # Handle multiple code blocks with regex
                        import re
                        # Match code blocks with language specification
                        pattern = r"```(\w+)?\n([\s\S]*?)```"
                        
                        def code_block_replacement(match):
                            lang = match.group(1) or ""
                            code = match.group(2)
                            return f'<pre><code class="language-{lang}">{code}</code></pre>'
                        
                        text = re.sub(pattern, code_block_replacement, text)
                        
                        # Convert inline code
                        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
                        
                        timestamp = msg.get("create_time", "")
                        
                        conversation.append({
                            "role": author,
                            "content": text,
                            "timestamp": timestamp,
                            "id": msg_id
                        })
                        logger.debug(f"Added {author} message to conversation")
            
            # Sort by timestamp if available
            conversation = sorted(conversation, key=lambda x: x.get("timestamp", ""))
            logger.debug(f"Sorted conversation has {len(conversation)} messages")
            
            # Build the HTML
            for msg in conversation:
                role = msg["role"]
                content = msg["content"]
                
                if role == "user":
                    html += f'<div class="user-message"><h3>User:</h3><div>{content}</div></div>\n'
                elif role == "assistant":
                    html += f'<div class="assistant-message"><h3>Assistant:</h3><div>{content}</div></div>\n'
                else:
                    html += f'<div class="system-message"><h3>{role}:</h3><div>{content}</div></div>\n'
        else:
            logger.warning("No 'mapping' found in API response")
            # Include whatever we got as debug information
            html += f"<div><h2>Debug: API Response Keys</h2><pre>{list(conversation_data.keys())}</pre></div>"
            # Potentially convert the entire JSON to a presentable format
            html += f"<div><h2>Conversation Data</h2><pre>{json.dumps(conversation_data, indent=2)}</pre></div>"
        
        html += "</body></html>"
        logger.info(f"Generated HTML for ChatGPT conversation with {len(conversation)} messages")
        return html
            
    except Exception as e:
        logger.error(f"Error generating HTML from conversation data: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
        
        # Generate error HTML
        html += "<div><h2>Error Generating Conversation</h2>"
        html += f"<p>An error occurred while processing the conversation data: {str(e)}</p>"
        html += "<h3>Raw Conversation Data:</h3>"
        html += f"<pre>{json.dumps(conversation_data, indent=2)}</pre>"
        html += "</div></body></html>"
        return html


def get_conversation_oauth(url, email=None, password=None, cookies=None):
    """
    Get conversation HTML content using OAuth authentication.
    """
    conversation_id = extract_conversation_id(url)
    if not conversation_id:
        logger.error("Failed to extract conversation ID from URL")
        return None
    
    logger.info(f"Getting conversation {conversation_id} via OAuth")
    
    # Check if we have a valid cached token
    if token_cache["access_token"] and token_cache["expires_at"]:
        if datetime.now() < token_cache["expires_at"]:
            logger.debug("Using cached access token")
            access_token = token_cache["access_token"]
        else:
            logger.debug("Cached token expired, getting new token")
            access_token = None
    else:
        logger.debug("No cached token available")
        access_token = None
    
    # If no valid token, try to get one
    if not access_token:
        if cookies:
            # Try getting token from cookies first
            logger.debug("Attempting to get token from cookies")
            access_token = get_access_token_from_cookies(cookies)
        
        if not access_token and email and password:
            # Fall back to email/password authentication
            logger.debug("Attempting to get token via OAuth flow")
            access_token = get_oauth_token(email, password)
    
    if not access_token:
        logger.error("Failed to obtain access token")
        return generate_error_html(conversation_id, "Authentication failed. Could not obtain access token.")
    
    # Use the access token to get conversation data
    conversation_data = get_conversation_api(conversation_id, access_token)
    
    if not conversation_data:
        logger.error("Failed to retrieve conversation data")
        return generate_error_html(conversation_id, "Could not retrieve conversation data using the access token.")
    
    # Generate HTML from conversation data
    html_content = generate_conversation_html(conversation_data, conversation_id)
    return html_content


def generate_error_html(conversation_id, message):
    """Generate an HTML page with error information."""
    html = "<!DOCTYPE html>\n<html><head><title>ChatGPT Error</title></head><body>\n"
    html += "<h1>Error: Unable to retrieve ChatGPT conversation</h1>\n"
    html += f"<h2>Conversation ID: {conversation_id}</h2>\n"
    html += f"<p>{message}</p>\n"
    html += "<p>Possible solutions:</p>\n"
    html += "<ul>\n"
    html += "<li>Provide valid OAuth credentials (email/password) using the --oauth-email and --oauth-password options</li>\n"
    html += "<li>Export fresh cookies from your browser and use the --cookie-json option</li>\n"
    html += "<li>Make sure you have access to this conversation in your ChatGPT account</li>\n"
    html += "</ul>\n"
    html += "</body></html>"
    return html
