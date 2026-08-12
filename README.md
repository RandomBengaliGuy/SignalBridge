# SignalBridge

<div align="center">
  <strong>An Omnichannel, AI-Powered Emergency Relay for the Deaf and Hard-of-Hearing</strong><br>
  <em>Connecting Victims, Volunteers, and 911 Dispatchers across the platforms they already use.</em>
</div>
<br>

<div align="center">
  <a href="INSERT_DEMO_VIDEO_LINK_HERE"><strong>  Watch the Full Demo Video Here</strong></a>
</div>

---

## The Problem

Deaf and hard-of-hearing individuals often cannot use voice-based emergency services (like 911) effectively. Text-to-911 support exists in patches, but it is inconsistent, slow, and lacks the ability to seamlessly coordinate live interpretation support or reliably relay context-rich information (like exact location or severity) the way a live voice call does. 

Accessibility ideas often stop at "a chat interface for the deaf." **The true insight is coordinating a three-party real-time relay** (the victim, the dispatcher, and a volunteer interpreter) seamlessly across the specific platforms each party already uses.

---

##  The Solution & Architecture

SignalBridge is an intelligent triage platform that acts as a central hub. It uses ultra-fast LLMs to extract emergency contexts and instantly routes the data across multiple platforms simultaneously.

```mermaid
flowchart LR
    %% Styling Classes for Caspian Theme (Vibrant Magenta/Pink)
    classDef default fill:#1E1E2E,stroke:#FF007F,stroke-width:2px,color:#FFFFFF,rx:10,ry:10
    classDef coreNode fill:#FF007F,stroke:#FFB3D9,stroke-width:4px,color:#FFFFFF,font-weight:bold,rx:15,ry:15
    classDef aiNode fill:#4D0026,stroke:#FF1A8C,stroke-width:2px,color:#FFD9EC,rx:10,ry:10
    classDef dbNode fill:#800040,stroke:#FF3399,stroke-width:2px,color:#FFFFFF,rx:10,ry:10
    classDef routeNode fill:#260013,stroke:#FF0055,stroke-width:2px,color:#FFB3CC,stroke-dasharray: 5 5,rx:10,ry:10

    %% Link Styling (Making the arrows match the theme)
    linkStyle default stroke:#FF007F,stroke-width:2px,color:#FFB3D9

    %% Intake
    T(Telegram) -->|Voice/Text| C{Caspian Core}
    E(Email) -->|Distress Email| C
    SMS(SMS/Offline) -->|Distress Text| C

    %% Core Processing
    C -->|Raw Payload| AI[Groq AI Extractor]
    AI -->|Location & Severity| DB[(Cloud PostgreSQL)]
    DB -->|Trigger Alerts| R{Channel Router}

    %% Dispatch Channels
    R --> S[Slack 911 Dispatcher]
    R --> D[Discord Volunteer Interpreters]
    R --> FG[Telegram Family Groups]
    R --> FE[Family Emails]
    R --> FS[Family SMS Phones]

    %% Bidirectional Bridges
    D -.->|Interpreter Chat Bridged| C
    S -.->|Status Updates Bridged| C

    %% Apply Styles to specific nodes
    class C coreNode;
    class AI aiNode;
    class DB dbNode;
    class R routeNode;
```

---

## Platform-by-Platform Integration

Because no single channel serves all three roles (Victims, Dispatchers, Interpreters), SignalBridge unifies them.

### 1. The Victim (Intake via Telegram)
<img src="https://github.com/user-attachments/assets/6a79e1b5-23c2-4f4d-b610-86ea591354cb" align="right" width="250">
The person in distress messages the SignalBridge Telegram bot. They use a simple, accessible interface they already use daily. If no location is provided, the system initiates a 15-second countdown requesting a Google Maps link.
<br><br>

### 2. 911 Dispatchers (Slack Integration)
<img src="INSERT_SLACK_IMAGE_URL_HERE" align="right" width="250">
Emergency services require structured, formal, rich-data reporting. Our AI instantly formats the panic text into a clean Dispatch Card detailing coordinates, nature, and severity. The dispatcher can click a button to acknowledge the alert.
<br><br>

### 3. Volunteer Interpreters (Discord Bridge)
<img src="INSERT_DISCORD_IMAGE_URL_HERE" align="right" width="250">
Specialized volunteers organize on community platforms like Discord. SignalBridge pings the volunteer channel requesting assistance. When a volunteer types `accept_relay:<id>`, SignalBridge establishes a **live, real-time two-way bridge** between Discord and the victim's Telegram.
<br><br>

### 4. Family Notifications (Email & SMS)
<img src="INSERT_EMAIL_SMS_IMAGE_URL_HERE" align="right" width="250">
Family members linked to the victim's account instantly receive offline alerts containing the exact coordinates and severity of the emergency.
<br><br>

> **SMS Infrastructure Note (Hackathon Constraints)**: 
> SignalBridge features a robust, hybrid SMS architecture. Out of the box, we safely mock outbound SMS alerts in the terminal to avoid strict international telecom regulations (like India's TRAI/DLT) which block programmatic SMS to local numbers without extensive corporate KYC and registration. 
> 
> However, our codebase is strictly **production-ready**: simply provide `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` in the `.env` file, and the Caspian SDK will dynamically switch from the mock gateway to routing live, real-world SMS alerts.

---

## Technology Stack

* **Backend Core**: Python, FastAPI
* **AI & Triage**: Groq (LLaMA 3) for lightning-fast entity extraction and natural language processing.
* **Database**: SQLite & SQLAlchemy. We implemented a robust relational database schema (`database.py`, `models.py`) to persistently track User Profiles (linked family members), Emergency States (triage, dispatched, resolved), and active Relay Sessions bridging different platforms.
* **Omnichannel Communications**: [Caspian SDK](https://trycaspianai.com/)
  * Used for cross-platform webhook abstraction, allowing a single lightweight `bot_client.py` file to seamlessly handle Telegram, Slack, Discord, and Email routing simultaneously.

---

## Running Locally

### Prerequisites
1. Python 3.9+
2. A Telegram Bot Token (from BotFather)
3. A Caspian AI Developer Account

### Setup
1. Clone the repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure your `.env` file:
   ```env
   GROQ_API_KEY=your_groq_key
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   CASPIAN_API_KEY=your_caspian_comm_key
   
   # Optional: For Live Twilio SMS
   TWILIO_ACCOUNT_SID=
   TWILIO_AUTH_TOKEN=
   TWILIO_PHONE_NUMBER=
   ```
3. Run the backend server:
   ```bash
   uvicorn main:app --reload
   ```
4. Authenticate your platforms! The terminal will print OAuth links for Slack and Discord. Click them to authorize the Caspian Agent in your respective workspaces.
5. In your Slack and Discord channels, type a message to the bot. Copy the `conv_...` ID from your terminal logs and add them to your `.env`:
   ```env
   SLACK_DISPATCH_CHANNEL=conv_abc123
   DISCORD_VOLUNTEER_CHANNEL=conv_xyz987
   ```

---

## License and Copyrights

- **Core Application**: MIT License. See `LICENSE` for more information.
- **Third-Party Integrations**: 
  - This project integrates with Slack, Discord, Telegram, and Twilio via the **Caspian AI SDK**. All platform logos and trademarks are the property of their respective owners. 
  - Generative AI processing provided by Groq Inc.

<br>
<div align="center">
</div>
