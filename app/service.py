"""Stateless exam result API; business state is stored outside this process."""
import json
import os
import re
import socket
from flask import Flask, jsonify, request
import psycopg2
import redis

app = Flask(__name__)
cache = redis.Redis(host=os.environ.get('REDIS_HOST', '127.0.0.1'),
                    password=os.environ.get('REDIS_PASSWORD'),
                    socket_timeout=0.2, socket_connect_timeout=0.2,
                    decode_responses=True)


def connect():
    return psycopg2.connect(host=os.environ['DB_HOSTS'], dbname='resultats',
                           user='resultats_app', password=os.environ['DB_PASSWORD'],
                           connect_timeout=2, target_session_attrs='read-write',
                           options='-c statement_timeout=1500')

@app.errorhandler(404)
def not_found(_error):
    return jsonify(error='not_found'), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return jsonify(error='method_not_allowed'), 405

@app.get('/info')
def info():
    return jsonify(hostname=socket.gethostname(), release=os.getenv('RELEASE', '1'))


@app.get('/sante')
def health():
    try:
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        finally:
            connection.close()
        return jsonify(status='ok')
    except (psycopg2.Error, UnicodeDecodeError):
        return jsonify(status='database_unavailable'), 503


@app.get('/resultat')
def result():
    matricule = request.args.get('matricule', '')
    if not re.fullmatch(r'[0-9]{6}', matricule):
        return jsonify(error='matricule must contain six digits'), 400
    key = 'resultats:v1:' + matricule
    enabled = os.environ.get('CACHE_ENABLED', '1') == '1'
    if enabled:
        try:
            value = cache.get(key)
            if value:
                return jsonify(json.loads(value))
        except (redis.RedisError, ValueError):
            pass
    try:
        connection = connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT matricule, nom, serie, moyenne, admis '
                               'FROM resultats WHERE matricule = %s', (matricule,))
                row = cursor.fetchone()
        finally:
            connection.close()
    except (psycopg2.Error, UnicodeDecodeError):
        return jsonify(error='database_unavailable'), 503
    if not row:
        return jsonify(error='not_found'), 404
    data = dict(zip(('matricule', 'nom', 'serie', 'moyenne', 'admis'), row))
    data['moyenne'] = float(data['moyenne'])
    if enabled:
        try:
            cache.setex(key, 30, json.dumps(data))
        except redis.RedisError:
            pass
    return jsonify(data)
