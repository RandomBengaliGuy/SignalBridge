import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

import httpx
# Initialize the Groq client with a custom httpx client to bypass the 'proxies' argument conflict
# caused by httpx>=0.28.0
custom_http_client = httpx.Client()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"), http_client=custom_http_client)

def transcribe_audio(audio_file_path: str) -> str:
    """
    Takes a path to an audio file (e.g., .ogg downloaded from Telegram)7
    and uses Groq's Whisper API to transcribe it into text.
    """
    try:
        with open(audio_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_file_path), file.read()),
                model="whisper-large-v3",
                prompt="Specify context or leave empty",  # Optional
                response_format="json",
                language="en", 
                temperature=0.0
            )
        return transcription.text
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return ""

def extract_emergency_details(text: str) -> dict:
    """
    Takes user text (or transcribed voice text) and uses Llama 3 on Groq
    to extract the severity and nature of the emergency into a structured JSON.
    """
    prompt = f"""
    You are an emergency extraction assistant. Read the following distress message 
    and extract the 'nature_of_emergency', 'severity' (Low, Medium, High, Critical), and 'location' (the address or place mentioned).
    
    CRITICAL INSTRUCTION: If the message is just a greeting (e.g. 'Hello', '/start') or clearly NOT an emergency, you MUST set 'nature_of_emergency' to 'FALSE_ALARM' and 'severity' to 'None'.
    If no location is mentioned, set 'location' to "Unknown".
    
    Respond ONLY with a valid JSON object matching this schema:
    {{
        "nature_of_emergency": "string",
        "severity": "string",
        "location": "string"
    }}
    
    Distress message: "{text}"
    """
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that only outputs valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="llama-3.1-8b-instant",
            temperature=0
        )
        
        result_text = chat_completion.choices[0].message.content.strip()
        print(f"----- GROQ OUTPUT DEBUG -----")
        print(result_text)
        print(f"-----------------------------")
        
        # Robustly extract JSON block using regex
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            raise ValueError("No JSON block found in the output.")
            
    except Exception as e:
        print(f"Error extracting details: {e}")
        # Fallback if the model fails
        return {
            "nature_of_emergency": "Unknown - Manual review required",
            "severity": "Unknown"
        }
