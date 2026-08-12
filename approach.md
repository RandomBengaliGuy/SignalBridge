# Approach: SignalBridge — Deaf/Hard-of-Hearing Emergency Relay

This document outlines the technical approach and implementation plan for the SignalBridge MVP, based on the finalized vision.

## Goal Description
Build a multi-channel emergency response orchestrator powered by the Caspian SDK. The system allows users in distress (particularly deaf or hard-of-hearing individuals) to report emergencies via a Telegram bot using either text or voice messages. The bot automatically requests GPS coordinates via a one-tap location button. 

Once the location and emergency context (severity, nature of emergency) are extracted using Groq (for fast LLM inference and Whisper voice-to-text), the system routes the emergency data to:
1. **Family/Friends:** WhatsApp and/or Discord groups that the user has pre-configured.
2. **Emergency Services:** A mocked API endpoint simulating 911 dispatch (police, ambulance, fire).

## Open Questions for the MVP Scope
1. **Live Interpreter Relay:** The original notes mentioned routing to a Discord channel to pull in a *volunteer sign-language interpreter* for a live relay conversation. The latest description focuses on notifying family WhatsApp/Discord groups. Do you want the MVP to include the live 2-way conversation relay with a volunteer interpreter, or should the MVP focus exclusively on the automated outbound alerts (to family groups and the mock dispatcher)?
2. **User Configuration:** For the 15-day MVP, instead of building a complex web dashboard for users to "connect" their WhatsApp/Discord groups, we will hardcode a dummy user profile in the backend that maps their Telegram ID to specific test WhatsApp/Discord group IDs. Is this acceptable for the MVP demo?

---

## Proposed Codebase Structure

We will build the MVP in a single cohesive Python codebase.

### Core Server & Bot Logic
The central hub for receiving and routing messages.

#### `main.py`
- Initialize `FastAPI` to serve as the web framework (useful for the mock dispatcher endpoint).
- Initialize `caspian-sdk`'s `CommClient`.
- Implement `@client.on_message` to listen for Telegram messages.
- Logic:
  - If the user sends `/sos` -> Respond with Telegram's "Share Location" button.
  - If the user sends text -> Run through Groq LLM to extract JSON (Nature of Emergency, Severity).
  - If the user sends a voice note -> Download `.ogg`, run through Groq Whisper API for text, then extract JSON.
  - Once location and details are collected -> Trigger `caspian` outbound messages to the configured WhatsApp/Discord groups.
  - Trigger HTTP POST to the mock dispatcher.

#### `mock_dispatch.py`
- A simple FastAPI router (`/api/dispatch`) that receives the emergency JSON payload.
- Logs the simulated alert to the console (simulating the screen in a 911 call center).

#### `ai_extractor.py`
- Contains the Groq API integration.
- `transcribe_audio(file_path)`: Uses Whisper API.
- `extract_emergency_details(text)`: Uses Groq LLM (e.g., Llama 3 on Groq) to return structured JSON.

---

## Verification & Testing Plan

1. **Intake Testing:** Open Telegram, send `/sos`, and tap "Share Location".
2. **Voice Processing:** Send a voice message saying "I am in a car accident and my arm is bleeding."
3. **AI Verification:** Verify that the backend successfully transcribes the audio and extracts the emergency details using Groq.
4. **Outbound 1 (Family):** Verify that a formatted alert containing the exact Latitude and Longitude is sent to the designated Discord/WhatsApp test group via Caspian.
5. **Outbound 2 (Dispatch):** Verify that the mock dispatch API receives the JSON payload.
