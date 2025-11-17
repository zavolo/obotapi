import json
from urllib.parse import parse_qs, unquote
from flask import Flask, request, jsonify, render_template
from logger import logger
from config import Config
from utils import normalize_params

def create_app(async_runner, request_processor):
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        return render_template('index.html', brand=Config.BRAND)
    
    @app.route('/bot<path:token_and_method>', methods=['GET', 'POST'])
    def bot_api(token_and_method):
        try:
            parts = token_and_method.strip('/').split('/')
            if len(parts) < 1:
                return jsonify({
                    "ok": False,
                    "error_code": 400,
                    "description": "Invalid request format"
                }), 400
            token = unquote(parts[0])
            method = parts[1] if len(parts) > 1 else ''
            if not method:
                return jsonify({
                    "ok": False,
                    "error_code": 400,
                    "description": "Method not specified"
                }), 400
            params = _extract_params(request)
            result = async_runner.run(
                request_processor.process(token, method, params)
            )
            status_code = 401 if result.get('error_code') == 401 else 200
            return jsonify(result), status_code
        except Exception as e:
            logger.error(f"Ошибка сервера: {e}", exc_info=True)
            return jsonify({
                "ok": False,
                "error_code": 500,
                "description": str(e)
            }), 500
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "ok": False,
            "error_code": 404,
            "description": "Not Found"
        }), 404
    return app

def _extract_params(request) -> dict:
    params = {}
    if request.method == 'POST':
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            params = request.get_json() or {}
        elif 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type:
            params = request.form.to_dict()
        elif request.data:
            try:
                params = json.loads(request.data.decode('utf-8'))
            except:
                try:
                    params = parse_qs(request.data.decode('utf-8'))
                    params = normalize_params(params)
                except:
                    params = {}
    else:
        params = parse_qs(request.query_string.decode('utf-8'))
        params = normalize_params(params)
    return params