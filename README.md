# Cloud Speech Memo Analyzer

A production-grade voice-powered memo analyzer built with Azure AI services. Record or upload audio, transcribe with Azure Speech, analyze with Azure Language, synthesize summaries with Text-to-Speech, and monitor everything with Azure Application Insights telemetry.

## 📁 Project Structure

```
CloudSpeechProject/
├── app/
│   ├── main.py                      # FastAPI app + all endpoints
│   ├── metrics.py                   # OpenTelemetry + custom metrics
│   ├── telemetry_log.py            # Session logging (in-memory)
│   ├── config.py                    # Configuration + constants
│   ├── schemas.py                   # Pydantic request/response models
│   ├── static/
│   │   └── index.html              # Full frontend (3 tabs: Analyzer, Stats, Telemetry)
│   └── services/
│       ├── transcription_service.py # Azure Speech SDK (batch mode)
│       ├── language_service.py      # Azure Language SDK (4 analyses)
│       ├── tts_service.py          # Azure Speech TTS (Neural voices)
│       ├── summary_service.py       # Summary text generation
│       ├── stats_service.py         # SQLite database (local stats)
│       └── audio_service.py         # Audio validation + temp file handling
├── telemetry.py                     # OpenTelemetry initialization
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables (git-ignored)
├── .gitignore                      # Ignore .env, *.db, etc.
├── transcription_stats.db          # SQLite database (auto-created)
└── README.md                        # This file
```




https://github.com/user-attachments/assets/3393e3f9-50fa-4fc9-b1ec-34caff2bebfc


## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (HTML/CSS/JS)                       │
│  • Audio recorder (MediaRecorder API → WAV conversion)          │
│  • File upload with drag-and-drop                               │
│  • Real-time results display (Analyzer, Stats, Telemetry tabs) │
│  • Session metrics dashboard                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python 3.12+)                      │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Stage 1: STT    │→ │  Stage 2: NLP    │→ │  Stage 3: TTS│  │
│  │ (Speech-to-Text) │  │ (Named Entities) │  │(Text-to-Spe) │  │
│  │  Azure Speech    │  │ Azure Language   │  │ Azure Speech │  │
│  │                  │  │ • Entities       │  │ Neural Voices│  │
│  │ • Transcription  │  │ • Key Phrases    │  │              │  │
│  │ • Confidence     │  │ • Sentiment      │  │ • Synthesis  │  │
│  │ • Word-level     │  │ • Analysis       │  │ • Base64 MP3 │  │
│  │   confidence     │  │                  │  │              │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
│                              ↓                                   │
│                    ┌──────────────────────┐                      │
│                    │  Telemetry & Metrics │                      │
│                    │                      │                      │
│                    │ • OpenTelemetry SDK  │                      │
│                    │ • Custom metrics     │                      │
│                    │ • Distributed traces │                      │
│                    │ • Session logging    │                      │
│                    └──────────────────────┘                      │
│                         ↓              ↓                          │
│              ┌──────────────────┐  ┌──────────────────────┐      │
│              │  Azure Monitor   │  │  SQLite Database     │      │
│              │ (App Insights)   │  │  (Local Stats)       │      │
│              └──────────────────┘  └──────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

**Pipeline Flow:**
1. **Audio Input** → Browser (WAV/MP3/OGG/AAC/M4A)
2. **Stage 1: Speech-to-Text** (Azure Speech) → Transcript + confidence scores
3. **Stage 2: Language Analysis** (Azure Language) → Entities, phrases, sentiment
4. **Stage 3: Text-to-Speech** (Azure Speech Neural) → Spoken summary (MP3)
5. **Results** → JSON response + HTML UI
6. **Telemetry** → OpenTelemetry metrics → Azure Application Insights + local SQLite

## 📋 Key Features

- **Real-time Audio Processing**: Record directly in browser or upload files (WAV, MP3, OGG, AAC, M4A)
- **Multi-Stage Pipeline**: Speech-to-Text → Language Analysis → Text-to-Speech
- **Confidence Scoring**: Word-level confidence tracking with automatic retry on low confidence
- **Language Support**: Detects language (en-US primary, en-GB fallback)
- **Entity Recognition**: Named entities, key phrases, sentiment analysis
- **Voice Selection**: 3 neural voices (Formal, Casual, Energetic)
- **Distributed Tracing**: Per-stage latency metrics visible in Azure Monitor
- **Session Dashboard**: Real-time metrics without needing Azure Portal
- **Database Logging**: SQLite persistence for historical analysis
- **Beautiful UI**: 3-tab interface (Analyzer, Stats, Session Telemetry)

## 🚀 Quick Start (Local Development)

### Prerequisites

- Python 3.12+
- Azure for Students account (or active Azure subscription)
- Azure CLI installed
- Git

### 1. Clone and Install

```bash
cd CloudSpeechProject
python -m venv cloud_venv
source cloud_venv/bin/activate
pip install -r requirements.txt
```

### 2. Create `.env` File

```bash
cat > .env << 'EOF'
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=eastus22
AZURE_LANGUAGE_KEY=your-language-key
AZURE_LANGUAGE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=...
WEBSITES_PORT=8000
EOF
```

### 3. Run Locally

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then visit: **http://localhost:8000**

## 🔧 Azure Resource Provisioning

All resources use the **F0 free tier**.

### Step 1: Install Azure CLI

```bash
az --version
az login
```

### Step 2: Create Resource Group

```bash
az group create \
  --name csc391-speech-rg \
  --location eastus22
```

### Step 3: Provision Azure Speech Service

```bash
# Create Speech resource (F0 = free)
az cognitiveservices account create \
  --name csc391-speech \
  --resource-group csc391-speech-rg \
  --kind SpeechServices \
  --sku F0 \
  --location eastus2 \
  --yes

# Retrieve the API key (save this in .env)
az cognitiveservices account keys list \
  --name csc391-speech \
  --resource-group csc391-speech-rg \
  --query "key1" --output tsv
```

### Step 4: Provision Azure Language Service

```bash
# Create Language resource (F0 = free)
az cognitiveservices account create \
  --name csc391-language \
  --resource-group csc391-speech-rg \
  --kind TextAnalytics \
  --sku F0 \
  --location eastus2 \
  --yes

# Retrieve the API key
az cognitiveservices account keys list \
  --name csc391-language \
  --resource-group csc391-speech-rg \
  --query "key1" --output tsv

# Retrieve the endpoint
az cognitiveservices account show \
  --name csc391-language \
  --resource-group csc391-speech-rg \
  --query properties.endpoint --output tsv
```

### Step 5: Provision Application Insights

```bash
# Step 5a: Create Log Analytics Workspace
az monitor log-analytics workspace create \
  --resource-group csc391-speech-rg \
  --workspace-name csc391-logs \
  --location eastus2

# Save the workspace ID (needed for next command)
WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group csc391-speech-rg \
  --workspace-name csc391-logs \
  --query id --output tsv)

# Step 5b: Create Application Insights
az monitor app-insights component create \
  --app csc391-insights \
  --location eastus2 \
  --resource-group csc391-speech-rg \
  --workspace $WORKSPACE_ID

# Step 5c: Retrieve the connection string (save in .env as APPLICATIONINSIGHTS_CONNECTION_STRING)
az monitor app-insights component show \
  --app csc391-insights \
  --resource-group csc391-speech-rg \
  --query connectionString --output tsv
```

### Step 6: Update `.env`

Copy all the retrieved values:

```bash
AZURE_SPEECH_KEY=<from-step-3>
AZURE_SPEECH_REGION=eastus2
AZURE_LANGUAGE_KEY=<from-step-4>
AZURE_LANGUAGE_ENDPOINT=<from-step-4>
APPLICATIONINSIGHTS_CONNECTION_STRING=<from-step-5c>
WEBSITES_PORT=8000
```

## Deploying to Azure Web App

### Step 1: Create Web App Resources

```bash
# Create App Service Plan (free tier: F1)
az appservice plan create \
  --name csc391-speech-plan \
  --resource-group csc391-speech-rg \
  --sku F1 \
  --is-linux

# Create Web App
az webapp create \
  --resource-group csc391-speech-rg \
  --plan csc391-speech-plan \
  --name csc391-speech-31024304 \
  --runtime "PYTHON|3.12"
```

### Step 2: Configure App Settings

```bash
# Enable build during deployment
az webapp config appsettings set \
  --name csc391-speech-31024304 \
  --resource-group csc391-speech-rg \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true

# Set startup file
az webapp config set \
  --startup-file "./startup.sh" \
  --name csc391-speech-31024304 \
  --resource-group csc391-speech-rg
```

### Step 3: Deploy Application

```bash
az webapp up \
  --resource-group csc391-speech-rg \
  --name csc391-speech-31024304 \
  --runtime "PYTHON:3.12"
```

### Step 4: Configure Environment Variables

```bash
az webapp config appsettings set \
  --name csc391-speech-31024304 \
  --resource-group csc391-speech-rg \
  --settings \
    AZURE_SPEECH_KEY="<your-key>" \
    AZURE_SPEECH_REGION="eastus2" \
    AZURE_LANGUAGE_KEY="<your-key>" \
    AZURE_LANGUAGE_ENDPOINT="<your-endpoint>" \
    APPLICATIONINSIGHTS_CONNECTION_STRING="<your-connection-string>"
```

### Step 5: View Deployment Logs

```bash
az webapp log tail \
  --name csc391-speech-31024304 \
  --resource-group csc391-speech-rg
```

### Step 6: Verify Deployment

```bash
az webapp browse \
  --resource-group csc391-speech-rg \
  --name csc391-speech-31024304
```

## 📊 API Endpoints

### Core Pipeline

| Endpoint | Method | Purpose | Input | Output |
|----------|--------|---------|-------|--------|
| `/` | GET | Load UI | — | HTML page |
| `/health` | GET | Health check | — | `{"status": "ok"}` |
| `/process` | POST | Full pipeline | Audio file + voice | Transcript + analysis + TTS |
| `/transcribe` | POST | Speech-to-Text only | Audio file | Transcript + confidence |
| `/analyze` | POST | Language analysis only | Text | Entities + phrases + sentiment |

### Utilities

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/voices` | GET | List 3 available TTS voices |
| `/stats` | GET | Database statistics (SQLite) |
| `/telemetry-summary` | GET | Session metrics (in-memory) |
| `/summary-audio` | GET | Convert text to audio |


## 📈 Monitoring & Telemetry

### 1. Session Dashboard (No Portal Needed)

Visit the **Session Telemetry** tab in the UI, or:

```bash
curl http://localhost:8000/telemetry-summary | jq .
```

Returns:
```json
{
  "total_calls": 5,
  "avg_confidence": 0.87,
  "min_confidence": 0.78,
  "max_confidence": 0.95,
  "avg_stt_ms": 1245.3,
  "avg_language_ms": 234.5,
  "avg_tts_ms": 456.2,
  "p95_stt_ms": 1834.5,
  "p95_language_ms": 412.3,
  "p95_tts_ms": 612.4,
  "sentiment_breakdown": {"positive": 2, "neutral": 2, "negative": 1},
  "recent_calls": [...]
}
```

### 2. Azure Portal — Transaction Traces

1. Go to Azure Portal → Application Insights → **csc391-insights**
2. Click **Monitoring** → **Transaction search**
3. Look for `/process` requests with waterfall showing:
   - `pipeline.process` (root)
     - `stage.speech_to_text` (child)
     - `stage.language_analysis` (child)
     - `stage.text_to_speech` (child)

### 3. Azure Portal — Custom Metrics

1. Click **Monitoring** → **Metrics**
2. Metric dropdown: search for `stage_stt_ms`, `stage_language_ms`, `stage_tts_ms`
3. Aggregation: **Avg**, **Min**, **Max**
4. Click **Pin to dashboard**

### 4. Azure Portal — KQL Queries

Go to **Monitoring** → **Logs** and run:

**Pipeline Stage Statistics:**
```kusto
customMetrics
| where timestamp > ago(1h)
| where name in ("stage_stt_ms", "stage_language_ms", "stage_tts_ms")
| summarize 
    avg_value = avg(value),
    p95_value = percentile(value, 95),
    call_count = count()
    by name
| order by name asc
```

**Confidence Trend:**
```kusto
customMetrics
| where timestamp > ago(2h)
| where name == "stt_confidence"
| project timestamp, confidence = value, audio_format = tostring(customDimensions["audio_format"])
| order by timestamp desc
```

**Request Traces with Events:**
```kusto
requests
| where timestamp > ago(1h)
| where name == "POST /process"
| project 
    timestamp,
    duration_ms = duration,
    success,
    stt_confidence = todouble(customDimensions["stt.confidence"]),
    event_name = tostring(customDimensions["event.name"])
| order by timestamp desc
```

## 🧪 Testing

```bash
# Run all tests
pytest -v

# Run only unit tests (no Azure calls)
pytest -q -m "not integration"

# Test the health endpoint
curl http://localhost:8000/health
```

## 🚨 Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "customMetrics not found" | Data hasn't propagated | Wait 3-5 minutes after first request |
| "Azure key invalid" | Wrong key or region | Verify in Azure Portal → Keys and Endpoint |
| "Microphone denied" | Not HTTPS/localhost | Use Azure Web App (HTTPS) or localhost |
| "Unsupported audio format" | Format not in whitelist | Upload WAV, MP3, OGG, or AAC |
| "Connection timeout" | Azure endpoint unreachable | Check firewall, verify endpoint URL |
| "Low confidence" | Noisy audio or unclear speech | Re-record or upload clearer audio |

## 📚 Key Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | HTML5 + CSS3 + Vanilla JS | UI, audio recording, results display |
| **Backend** | FastAPI + Python 3.12 | REST API, pipeline orchestration |
| **Audio (Browser)** | Web Audio API + MediaRecorder | Browser recording + WAV encoding |
| **Audio (Cloud)** | Azure Speech SDK | Speech-to-Text recognition |
| **NLP** | Azure Language SDK | Entity extraction, key phrases, sentiment |
| **TTS** | Azure Speech SDK (Neural) | Text-to-Speech synthesis |
| **Telemetry** | OpenTelemetry SDK | Metrics, traces, spans |
| **Monitoring** | Azure Application Insights | Distributed tracing, custom metrics, KQL |
| **Database** | SQLite | Local persistence of statistics |
