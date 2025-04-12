## 🚀 Setup

Follow these steps to get the project running locally:

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Create and Activate a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate          # On macOS/Linux
venv\Scripts\activate             # On Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Add API Keys and Credentials
Place the following files in the project root:
- `api_key.txt` – your Gemini or Google Generative AI API key
- `credentials.json` – your Gmail API OAuth2 credentials

---

### 🔑 Required Google APIs

Ensure these APIs are enabled in your [Google Cloud Console](https://console.cloud.google.com/):

1. **Gmail API**  
   For accessing and analyzing email threads

2. **People API** *(optional but recommended)*  
   To resolve contact names and enrich email data

3. **Generative Language API** (Gemini / PaLM API)  
   For summarization, tagging, and relationship intelligence

To enable these:
- Go to [Google Cloud Console > APIs & Services](https://console.cloud.google.com/apis/library)
- Select your project
- Search for each API and click "Enable"

---

### 5. Set Up a Local MongoDB Database
Create a directory for MongoDB data:
```bash
mkdir -p ./data/db
```

### 6. Start MongoDB Locally
Run the MongoDB daemon using your local data path:
```bash
mongod --dbpath $(pwd)/data/db
```

> 📌 **Note**: Make sure MongoDB is installed on your machine. If not, see [MongoDB installation guide](https://docs.mongodb.com/manual/installation/).
