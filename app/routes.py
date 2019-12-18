from flask import render_template, redirect, url_for, flash, request
from app import app

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html',  title='Close <> RingCentral Connector')