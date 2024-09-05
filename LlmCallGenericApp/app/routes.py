from flask import Blueprint, request, jsonify

main = Blueprint('main', __name__)

@main.route('/ask-llm', methods=['POST'])
def ask_llm():
    data = request.get_json()
    if 'input_string' not in data:
        return jsonify({'error': 'No input_string provided'}), 400
    input_string = data['input_string']
    upper_case_string = input_string.upper()
    return jsonify({'result': upper_case_string})
