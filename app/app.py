from flask import Flask, send_file
import os

app = Flask(__name__)

@app.get("/")
def portifolio():
    return send_file('portifolio.html', mimetype='text/html')

@app.get("/portifolio.html")
def portifolio():
    return send_file('portifolio.html', mimetype='text/html')

@app.get("/lancheira.webp")
def lancheira_webp():
    return send_file('imagens/lancheira.webp', mimetype='image/webp')

@app.get("/politica-privacidade.html")
def politica_privacidade():
    return send_file('politica-privacidade.html', mimetype='text/html')

@app.get("/termos-de-uso.html")
def termos_de_uso():
    return send_file('termos-de-uso.html', mimetype='text/html')

@app.get("/contato.html")
def contato():
    return send_file('contato.html', mimetype='text/html')

@app.get("/lanche.html")
def home():
    return send_file('lanche.html', mimetype='text/html')
