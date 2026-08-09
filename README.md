# SignalBridge
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
