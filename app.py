from flask import Flask, request, jsonify, render_template
import requests
import datetime

app = Flask(__name__)

API_KEY = "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"
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
    user_input = request.json.get("question", "")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_input}]
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions", headers=HEADERS, json=payload)
    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    with open("search_history.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now()}\\nQ: {user_input}\\nA: {answer}\\n\\n")

    return jsonify({"response": answer})


if __name__ == "__main__":
    app.run(debug=True)
