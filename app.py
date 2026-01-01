from flask import Flask, request, jsonify, render_template
import requests
import datetime
import os
import logging
from functools import wraps
import time

app = Flask(__name__)

# Configure logging for production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Loading OpenRouter API key from environment variable with fallback checks
API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY") or os.getenv("OPENROUTER_API_KEY")

# WORKING FREE MODEL (updated for 2025)
MODEL = "meta-llama/llama-3.3-70b-instruct:free"  # Fast, reliable, rarely rate-limited

# Debug logging - show all environment variables that contain 'OPENROUTER'
openrouter_vars = {k: v[:20] + '...' if v else 'None' for k, v in os.environ.items() if 'OPENROUTER' in k.upper()}
logger.info(f"OpenRouter env vars found: {openrouter_vars if openrouter_vars else 'NONE'}")
logger.info(f"API Key loaded: {'Yes' if API_KEY else 'NO - CHECK ENVIRONMENT VARIABLES!'}")

# List all env vars for debugging (first 10 characters only for security)
all_env_vars = list(os.environ.keys())
logger.info(f"Total environment variables available: {len(all_env_vars)}")
logger.info(f"Sample env vars: {all_env_vars[:5]}")

# Validate API key on startup
if not API_KEY:
    logger.error("=" * 50)
    logger.error("CRITICAL: OPENROUTER_API_KEY environment variable not set!")
    logger.error("Available env vars: " + ", ".join(all_env_vars))
    logger.error("=" * 50)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": os.environ.get("RENDER_EXTERNAL_URL", "https://your-app.onrender.com"),
    "X-Title": "ThinkFlow AI Assistant"
}

# Rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 1

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global last_request_time
        current_time = time.time()
        if current_time - last_request_time < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - (current_time - last_request_time))
        last_request_time = time.time()
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/health")
def health():
    """Health check endpoint for debugging"""
    return jsonify({
        "status": "running",
        "api_key_configured": bool(API_KEY),
        "model": MODEL,
        "env_vars_count": len(os.environ),
        "has_openrouter_key": "OPENROUTER_API_KEY" in os.environ
    })

@app.route("/ask", methods=["POST"])
@rate_limit
def ask():
    try:
        # Check API key first
        if not API_KEY:
            logger.error("API key not available in request")
            logger.error(f"Environment variables available: {list(os.environ.keys())}")
            return jsonify({
                "response": "API configuration error. The OPENROUTER_API_KEY environment variable is not set. Please configure it in your hosting platform."
            }), 500

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_input = data.get("question", "").strip()
        if not user_input:
            return jsonify({"response": "Please provide a question to get started."}), 400

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are ThinkFlow, a helpful and intelligent AI assistant. Provide clear, informative, and engaging responses. Keep answers concise and practical."
                },
                {
                    "role": "user", 
                    "content": user_input
                }
            ],
            "max_tokens": 800,  # Slightly reduced for faster responses
            "temperature": 0.7,
            "top_p": 0.9
        }

        logger.info(f"Processing question: {user_input[:50]}...")
        logger.info(f"Using model: {MODEL}")

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        logger.info(f"OpenRouter response status: {response.status_code}")

        if response.status_code == 401:
            logger.error("Unauthorized: Check API key")
            logger.error(f"API Key (first 10 chars): {API_KEY[:10] if API_KEY else 'None'}")
            return jsonify({"response": "Authentication error. The API key appears to be invalid. Please check your OpenRouter API key."}), 500
        elif response.status_code == 404:
            error_data = response.json()
            logger.error(f"Model not found: {error_data}")
            return jsonify({"response": f"Model error: {error_data.get('error', {}).get('message', 'Model not available')}"}), 500
        elif response.status_code == 429:
            logger.warning("Rate limited")
            return jsonify({"response": "Too many requests. Please wait a moment and try again."}), 429
        elif response.status_code != 200:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return jsonify({"response": "Sorry, I'm having trouble processing your request right now. Please try again later."}), 500

        data = response.json()

        if not data.get("choices") or not data["choices"]:
            logger.error(f"Empty response from API: {data}")
            return jsonify({"response": "I received an empty response. Please try rephrasing your question."}), 500

        answer = data["choices"][0]["message"]["content"].strip()

        if not answer:
            return jsonify({"response": "I'm not sure how to respond to that. Could you try asking in a different way?"}), 500

        # Save to history (with error handling for read-only filesystems)
        try:
            history_file = os.path.join(os.path.dirname(__file__), "search_history.txt")
            with open(history_file, "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}]\n")
                f.write(f"Q: {user_input}\n")
                f.write(f"A: {answer}\n")
                f.write("-" * 50 + "\n\n")
        except Exception as e:
            logger.warning(f"Could not save to history (this is normal on some platforms): {str(e)}")

        logger.info("Response generated successfully")
        return jsonify({"response": answer})

    except requests.exceptions.Timeout:
        logger.error("Request timeout")
        return jsonify({"response": "Request timed out. Please try again."}), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return jsonify({"response": "Network error. Please check your connection and try again."}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"response": "An unexpected error occurred. Please try again."}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# For local development
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
