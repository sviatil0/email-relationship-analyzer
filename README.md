# 💌 Email Relationship Analyzer

This project is an automated relationship intelligence tool that connects to your Gmail account, processes your sent email threads, and uses a large language model (Gemini) to analyze your communications. It identifies important participants, tags the interaction, summarizes the context, and assigns a sentiment score. All this data is then stored in a structured format in a MongoDB database.

---

## ✅ What This Program Does

1. **🔐 Authenticates with Google APIs**  
   Uses OAuth 2.0 to authorize access to Gmail and People APIs.

2. **📬 Retrieves Sent Email Threads**  
   Gathers all sent threads from your Gmail account and extracts metadata such as participants and messages.

3. **🧹 Cleans & Parses Conversations**  
   Strips quoted replies and signatures, preserving only the clean message content.

4. **💡 Analyzes with Gemini AI**  
   Sends each thread to the Gemini model to:
   - Identify non-owner participants
   - Classify primary relationships (e.g., recruiter, client)
   - Generate contextual tags
   - Summarize the interaction
   - Estimate sentiment score
   - Flag irrelevant or spammy threads with `"AVOID"`

5. **📦 Stores Structured Results in MongoDB**  
   Stores each person's info in a `people` collection, maintaining running sentiment and message stats. Tags are managed separately.

6. **🚀 Multithreaded Performance**  
   Uses `ProcessPoolExecutor` to process email threads in parallel based on the number of available CPU cores.

---

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
- `api_key.txt` – your Gemini or Google API key
- `credentials.json` – your Gmail API credentials (OAuth2)

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
