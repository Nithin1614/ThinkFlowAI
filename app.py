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

# Loading OpenRouter API key from environment variable
API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL = "mistralai/mistral-7b-instruct"

# Debug for Render/Gunicorn
logger.info(f"API Key loaded: {'Yes' if API_KEY else 'No'}")

# Validate API key on startup
if not API_KEY:
    logger.error("OPENROUTER_API_KEY environment variable not set!")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://your-app.onrender.com",  # Update with your Render URL
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

@app.route("/ask", methods=["POST"])
@rate_limit
def ask():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_input = data.get("question", "").strip()
        if not user_input:
            return jsonify({"response": "Please provide a question to get started."}), 400

        if not API_KEY:
            logger.error("API key not available")
            return jsonify({"response": "API configuration error. Please check server settings."}), 500

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are ThinkFlow, a helpful and intelligent AI assistant. Provide clear, informative, and engaging responses."
                },
                {
                    "role": "user", 
                    "content": user_input
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.7,
            "top_p": 0.9
        }

        logger.info(f"Processing question: {user_input[:50]}...")

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code == 401:
            logger.error("Unauthorized: Check API key")
            return jsonify({"response": "Authentication error. Please check API configuration."}), 500
        elif response.status_code == 429:
            logger.warning("Rate limited")
            return jsonify({"response": "Too many requests. Please wait a moment and try again."}), 429
        elif response.status_code != 200:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return jsonify({"response": "Sorry, I'm having trouble processing your request right now. Please try again later."}), 500

        data = response.json()

        if not data.get("choices") or not data["choices"]:
            return jsonify({"response": "I received an empty response. Please try rephrasing your question."}), 500

        answer = data["choices"][0]["message"]["content"].strip()

        if not answer:
            return jsonify({"response": "I'm not sure how to respond to that. Could you try asking in a different way?"}), 500

        # Save to history
        try:
            with open("search_history.txt", "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}]\n")
                f.write(f"Q: {user_input}\n")
                f.write(f"A: {answer}\n")
                f.write("-" * 50 + "\n\n")
        except Exception as e:
            logger.warning(f"Could not save to history: {str(e)}")

        logger.info("Response generated successfully")
        return jsonify({"response": answer})

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"response": "An unexpected error occurred. Please try again."}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

# For Gunicorn - don't include the if __name__ == "__main__" block
# Gunicorn will handle the server startup
