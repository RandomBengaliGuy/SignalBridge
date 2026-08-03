import os
import json
import re
from groq import Groq
from dotenv import load_dotenv
import httpx

load_dotenv()
client = Groq(api_key=os.environ.get('GROQ_API_KEY'), http_client=httpx.Client())

text = 'I am trapped in a fire'
prompt = f"""
You are an emergency extraction assistant. Read the following distress message 
and extract the 'nature_of_emergency' and 'severity' (Low, Medium, High, Critical).

Respond ONLY with a valid JSON object matching this schema:
{{
    "nature_of_emergency": "string",
    "severity": "string"
}}

Distress message: "{text}"
"""

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {'role': 'system', 'content': 'You are a helpful assistant that only outputs valid JSON.'},
            {'role': 'user', 'content': prompt}
        ],
        model='llama-3.1-8b-instant',
        temperature=0
    )

    result_text = chat_completion.choices[0].message.content.strip()
    print('RAW OUTPUT:')
    print(result_text)

    match = re.search(r'\{.*\}', result_text, re.DOTALL)
    if match:
        print('SUCCESS:', json.loads(match.group(0)))
    else:
        print('FAILED NO MATCH')
except Exception as e:
    print("GROQ EXCEPTION:", e)
