from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
import datetime
import os

app = Flask(__name__)

# Load your OpenRouter API key from environment variable
API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL = "mistralai/mistral-7b-instruct"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    user_input = request.json.get("question", "").strip()
    if not user_input:
        return jsonify({"response": "Question is empty."}), 400

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_input}]
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json=payload
        )

        if response.status_code != 200:
            return jsonify({"response": "Sorry, something went wrong with the AI response."}), 500

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        # Save to search history
        with open("search_history.txt", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now()}\nQ: {user_input}\nA: {answer}\n\n")

        return jsonify({"response": answer})

    except Exception as e:
        return jsonify({"response": f"Internal Server Error: {str(e)}"}), 500

# Serve static history file
@app.route("/static/<path:path>")
def static_proxy(path):
    return send_from_directory(".", path)

if __name__ == "__main__":
    app.run(debug=True)
