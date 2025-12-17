from flask import Flask, render_template, redirect, url_for, request, jsonify
import json
import requests

API_GATEWAY_URL = "http://api-gateway:8000"

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static'
)


@app.route('/')
def login():
    return render_template('login.html')


@app.route('/account')
def account():
    return render_template('doclist.html')


@app.route('/api/userdocs/<username>')
def get_user_docs(username):
    
    user_resp = requests.get(f"{API_GATEWAY_URL}/users/username/{username}")

    if user_resp.status_code != 200:
        return jsonify({"my_docs": [], "shared_docs": []})
    
    user_data = user_resp.json()
    user_id = user_data["id"]
    
    docs_resp = requests.get(f"{API_GATEWAY_URL}/documents/user/{user_id}")
    
    if docs_resp.status_code != 200:
        return jsonify({"error": "Failed to fetch documents"}), 500
    
    docs = docs_resp.json()

    result = {
        "my_docs": [],
        "shared_docs": []
    }

    for doc in docs:
        result["my_docs"].append({
            "id": doc["id"],
            "title": doc["title"],
            "content": doc["content"],
            "created_at": doc["created_at"],
            "modified_at": doc.get("updated_at"),
            "shared_to": []
        })

    return jsonify(result)

@app.route('/users/<user>/documents/<document>')
def user_doc(user, document):
    return render_template('docview.html')
    # TODO



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
