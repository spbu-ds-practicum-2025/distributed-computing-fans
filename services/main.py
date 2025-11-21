
from flask import Flask, render_template, redirect, url_for, request, jsonify
import json


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
    with open("mock_db.json", encoding='utf-8') as f:
        db = json.load(f)
    user_data = db.get(username)
    if user_data:
        return jsonify(user_data)
    else:
        return jsonify({"error": "User not found"}), 404


@app.route('/users/<user>/documents/<document>')
def user_doc(user, document):
    return render_template('docview.html')
    # TODO



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
