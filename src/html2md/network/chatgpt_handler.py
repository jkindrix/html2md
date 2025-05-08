"""
Special handler for accessing ChatGPT content.
"""

import json
import logging
import re
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger("chatgpt_handler")


def extract_conversation_id(url):
    """Extract conversation ID from ChatGPT URL."""
    # Format: https://chatgpt.com/c/6812d27d-6498-8006-9c6e-e6b6a4d6c0eb
    match = re.search(r'chatgpt\.com/c/([a-zA-Z0-9-]+)', url)
    if match:
        return match.group(1)
    
    # Check for other URL formats
    parsed_url = urlparse(url)
    if parsed_url.netloc == "chatgpt.com" or parsed_url.netloc == "chat.openai.com":
        path_parts = parsed_url.path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[0] == 'c':
            return path_parts[1]
    
    return None


def get_conversation_html(url, session, headers):
    """Get conversation HTML content using cookies from session."""
    conversation_id = extract_conversation_id(url)
    if not conversation_id:
        logger.error("Failed to extract conversation ID from URL")
        return None
    
    logger.info(f"Extracted conversation ID: {conversation_id}")
    
    # Approach 1: Directly get the HTML page
    try:
        logger.info("Attempting direct HTML retrieval")
        
        # Debug cookie information to see what's available
        logger.debug(f"Available cookies for session: {session.cookies.get_dict()}")
        
        # Add required headers for ChatGPT
        chat_headers = headers.copy()
        chat_headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-CH-UA": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://chatgpt.com/"
        })
        
        logger.debug(f"Headers being used: {chat_headers}")
        
        response = session.get(url, headers=chat_headers, timeout=30)
        
        # Log detailed response info
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response headers: {response.headers}")
        
        # Log the first 200 characters of the response for debugging
        if response.text:
            logger.debug(f"First 200 chars of response: {response.text[:200]}")
        
        if response.status_code == 200 and len(response.text) > 1000:
            logger.info("Successfully retrieved conversation HTML directly")
            return response.text
        else:
            # Log more details about what might be wrong
            if response.status_code != 200:
                logger.warning(f"Direct HTML request failed with status {response.status_code}")
            elif len(response.text) <= 1000:
                logger.warning(f"Response too small: {len(response.text)} bytes")
                # Check if it's an error page
                if "error" in response.text.lower() or "not found" in response.text.lower():
                    logger.warning("Response appears to be an error page")
                # Check if it's a login page
                if "log in" in response.text.lower() or "sign in" in response.text.lower():
                    logger.warning("Response appears to be a login page - authentication failed")
            
            logger.debug(f"First 500 chars of failed response: {response.text[:500]}")
            
    except Exception as e:
        logger.error(f"Error in direct HTML retrieval: {e}")
    
    # Approach 2: Try API endpoint to get conversation data
    try:
        logger.info("Attempting API-based retrieval")
        # Check if we're dealing with chat.openai.com or chatgpt.com
        domain = "chatgpt.com"
        if "chat.openai.com" in url:
            domain = "chat.openai.com"
            
        api_url = f"https://{domain}/backend-api/conversation/{conversation_id}"
        logger.debug(f"API URL: {api_url}")
        
        # Dump cookies again to see if they change
        logger.debug(f"Cookies available for API request: {session.cookies.get_dict()}")
        
        # Update headers for API request
        api_headers = headers.copy()
        api_headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authority": domain,
            "Origin": f"https://{domain}",
            "Referer": url,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        })
        
        logger.debug(f"API Request Headers: {api_headers}")
        
        api_response = session.get(api_url, headers=api_headers, timeout=30)
        
        logger.debug(f"API Response Status: {api_response.status_code}")
        logger.debug(f"API Response Headers: {api_response.headers}")
        
        if api_response.text:
            logger.debug(f"First 500 chars of API response: {api_response.text[:500]}")
        
        if api_response.status_code == 200:
            logger.info("Successfully retrieved conversation data from API")
            
            try:
                data = api_response.json()
                logger.debug(f"API returned JSON with keys: {list(data.keys())}")
                
                # Build HTML structure with conversation data
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
                
                if "mapping" in data:
                    logger.debug(f"Found 'mapping' with {len(data['mapping'])} entries")
                    # Extract messages and rebuild conversation
                    messages = data.get("mapping", {})
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
                    html += f"<div><h2>Debug: API Response Keys</h2><pre>{list(data.keys())}</pre></div>"
                
                html += "</body></html>"
                logger.info(f"Generated HTML for ChatGPT conversation with {len(conversation)} messages")
                return html
            
            except json.JSONDecodeError:
                logger.error("Failed to parse API response as JSON")
                logger.debug(f"Response content: {api_response.text[:500]}...")
        else:
            logger.warning(f"API request failed with status {api_response.status_code}")
            if api_response.status_code == 401:
                logger.error("Authentication failed. Make sure you have valid cookies.")
                logger.debug(f"Response on 401: {api_response.text[:500]}")
            elif api_response.status_code == 403:
                logger.error("Access forbidden. OpenAI might be blocking the request.")
                logger.debug(f"Response on 403: {api_response.text[:500]}")
            elif api_response.status_code == 404:
                logger.error("Conversation not found. It might have been deleted or you don't have access to it.")
                logger.debug(f"Response on 404: {api_response.text[:500]}")
            else:
                # For other error codes
                logger.error(f"Unexpected status code: {api_response.status_code}")
                logger.debug(f"Response: {api_response.text[:500]}")
    
    except Exception as e:
        logger.error(f"Error while accessing ChatGPT API: {e}")
        # More detailed error info
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    # Approach 3: Fall back to a simplified API call if possible
    try:
        logger.info("Attempting simplified API retrieval")
        # Some older conversations might be accessible through a different endpoint
        alternate_api_url = f"https://chatgpt.com/api/conversation/{conversation_id}"
        
        simplified_headers = headers.copy()
        simplified_headers.update({
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        })
        
        logger.debug(f"Alternate API URL: {alternate_api_url}")
        logger.debug(f"Simplified headers: {simplified_headers}")
        
        alt_response = session.get(alternate_api_url, headers=simplified_headers, timeout=30)
        logger.debug(f"Alternate API Response Status: {alt_response.status_code}")
        
        if alt_response.status_code == 200:
            logger.info("Successfully retrieved conversation data from alternate API")
            try:
                alt_data = alt_response.json()
                html = f"<!DOCTYPE html>\n<html><head><title>ChatGPT Conversation</title></head><body>\n"
                html += f"<h1>ChatGPT Conversation ({conversation_id})</h1>\n"
                html += f"<pre>{json.dumps(alt_data, indent=2)}</pre>\n"
                html += "</body></html>"
                return html
            except Exception as e:
                logger.error(f"Error processing alternate API response: {e}")
                logger.debug(f"Response: {alt_response.text[:500]}")
        else:
            logger.warning(f"Alternate API request failed with status {alt_response.status_code}")
            logger.debug(f"Response: {alt_response.text[:500] if alt_response.text else 'No response body'}")
    except Exception as e:
        logger.error(f"Error accessing alternate API: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    # Approach 4: Try using the access token from cookie directly
    try:
        logger.info("Attempting direct access token method")
        
        # Try to extract access token from cookies
        access_token = None
        session_token = None
        
        # Look for relevant tokens in cookies
        for cookie_name in session.cookies.keys():
            if "token" in cookie_name.lower() or "session" in cookie_name.lower():
                logger.debug(f"Found potential token cookie: {cookie_name}")
                if "__Secure-next-auth.session-token" == cookie_name:
                    session_token = session.cookies.get(cookie_name)
                    logger.debug("Found session token cookie")
                if "access_token" in cookie_name.lower():
                    access_token = session.cookies.get(cookie_name)
                    logger.debug("Found access token cookie")
        
        if session_token:
            logger.debug("Using session token for authentication")
            # Try using the session token to get the conversation directly
            auth_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Authorization": f"Bearer {session_token}"
            }
            
            # Try a different API endpoint
            user_api_url = "https://chat.openai.com/api/auth/session"
            user_response = session.get(user_api_url, headers=auth_headers, timeout=30)
            
            if user_response.status_code == 200:
                logger.debug("Successfully retrieved user session from API")
                try:
                    user_data = user_response.json()
                    if "accessToken" in user_data:
                        access_token = user_data["accessToken"]
                        logger.debug("Obtained access token from session API")
                except Exception as e:
                    logger.error(f"Error parsing user session response: {e}")
            
            if access_token:
                logger.debug("Using obtained access token for conversation API")
                # Now use the access token to get the conversation
                token_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
                
                conversation_api_url = f"https://chat.openai.com/backend-api/conversation/{conversation_id}"
                token_response = session.get(conversation_api_url, headers=token_headers, timeout=30)
                
                if token_response.status_code == 200:
                    logger.info("Successfully retrieved conversation with access token")
                    try:
                        conversation_data = token_response.json()
                        # Build a basic HTML for the conversation
                        html = f"<!DOCTYPE html>\n<html><head><title>ChatGPT Conversation</title></head><body>\n"
                        html += f"<h1>ChatGPT Conversation ({conversation_id})</h1>\n"
                        html += f"<div>Retrieved using access token method</div>\n"
                        html += f"<pre>{json.dumps(conversation_data, indent=2)}</pre>\n"
                        html += "</body></html>"
                        return html
                    except Exception as e:
                        logger.error(f"Error processing conversation response: {e}")
                else:
                    logger.warning(f"Conversation API with token failed: {token_response.status_code}")
    except Exception as e:
        logger.error(f"Error in access token approach: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
    
    logger.error("All approaches to retrieve ChatGPT conversation content failed")
    # Return a diagnostic HTML page instead of None
    html = f"<!DOCTYPE html>\n<html><head><title>ChatGPT Error</title></head><body>\n"
    html += f"<h1>Error: Unable to retrieve ChatGPT conversation</h1>\n"
    html += f"<h2>Conversation ID: {conversation_id}</h2>\n"
    html += f"<p>All attempts to retrieve the conversation content failed. Possible reasons:</p>\n"
    html += f"<ul>\n"
    html += f"<li>Authentication cookies are missing or expired</li>\n"
    html += f"<li>The conversation may be inaccessible or deleted</li>\n"
    html += f"<li>Your access to this conversation may be restricted</li>\n"
    html += f"<li>ChatGPT's API structure may have changed</li>\n"
    html += f"</ul>\n"
    html += f"<p>Try exporting fresh cookies and using the --cookie-json option again.</p>\n"
    html += f"</body></html>"
    return html


def is_chatgpt_url(url):
    """Check if URL is a ChatGPT conversation."""
    # Check for chatgpt.com and chat.openai.com domains with conversation paths
    if any(domain in url for domain in ["chatgpt.com/c/", "chat.openai.com/c/", "chat.openai.com/share/"]):
        return True
        
    # Check for domain match
    from urllib.parse import urlparse
    parsed_url = urlparse(url)
    if parsed_url.netloc in ["chatgpt.com", "chat.openai.com"]:
        # Check for conversation path patterns
        path = parsed_url.path
        if path.startswith("/c/") or path.startswith("/share/") or "/conversation/" in path:
            return True
    
    return False