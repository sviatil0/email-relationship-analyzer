import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
# from pprint import pprint # For debuggin only
# from google.cloud import language_v1 # For another way to do sentiment processing
import sys
# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/userinfo.profile" ] 
from pymongo import MongoClient
from google import genai
from google.genai import types
import json
from concurrent.futures import ProcessPoolExecutor
with open("api_key.txt") as api_key_file:
    API_KEY= api_key_file.readline().strip()

## Leave another way to identify sentiment out there
# def identify_sentiment(text:str) -> int:
#     '''
#     Identifies sentiment based on the body of text. 
#     '''
#     client = language_v1.LanguageServiceClient()

#     # The text to analyze.
#     document = language_v1.types.Document(
#         content=text, type_=language_v1.types.Document.Type.PLAIN_TEXT
#     )

#     # Detects the sentiment of the text.
#     sentiment = client.analyze_sentiment(
#         request={"document": document}
#     ).document_sentiment

#     return sentiment
def authorize_account(app_credentials_path : str="credentials.json", user_token_path : str ="token.json")->str:
    '''
    Authorize the google account based with read only scope + metadata scope
    '''
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # timej.
    # Check if there are user credentials stored in tocken.json
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # Will probably asked to reloging every time since ask for sensive scope 
    # If not or credentials are invalid 
    if not creds or not creds.valid:
        if creds and creds.expired:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(app_credentials_path, SCOPES) 
            creds = flow.run_local_server(port=0)

    try:
        service = build("gmail", "v1", credentials=creds)
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        with open("token.json", "w") as token:
            token.write(creds.to_json())
        if labels:
            print("Google API activated successfully and user authorized!")
        else:
            print("Something went wrong")
            sys.exit(1)
    except HttpError as err:
        print(f"{err} occured")
        sys.exit(1)
    return creds
def get_sent_messages_threads(service):
    """Gets a list of all the messageIds and corresponding threadIds in the SENT folder"""
    next_page_tocken = None
    thread_ids = set()
    while True:
        response = service.users().messages().list(
            userId='me',
            labelIds=['SENT'],
            pageToken = next_page_tocken
            ).execute() # is a dictonary
        messages = response.get('messages', [])
        for item in messages:
            thread_ids.add(item['threadId'])
        next_page_tocken = response.get("nextPageToken") 
        if(not next_page_tocken):
            break
    return list(thread_ids)

def get_owner_dic(gmail_service,people_service):
    """Fetches the authenticated user's email address from Gmail API."""
    # Get email from Gmail API
    profile = gmail_service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Get full name from People API
    person = people_service.people().get(
        resourceName="people/me",
        personFields="names"
    ).execute()
    name = person.get("names", [{}])[0].get("displayName", "Unknown")

    return {
        "email": email,
        "name": name
    }

def process_gmail_thread(service, thread_id, account_owner_email):
    """
    Process a Gmail thread by concatenating emails in chronological order,
    removing repetition, and prefixing each message with the sender's name.
    Also extracts all participants except the account owner.
    
    Args:
        service: Authenticated Gmail API service object
        thread_id: ID of the Gmail thread to process
        account_owner_email: Email address of the account owner to exclude from participants list
        
    Returns:
        A dictionary containing:
            - 'participants': Dict of participant emails and names (excluding account owner)
            - 'thread': Processed conversation text
    """
    try:
        # Get the thread with full message details
        thread = service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()
        
        # Initialize result dictionary
        result = {
            'participants': {},
            'thread': ''
        }
        
        # Placeholder for the processed conversation
        processed_conversation = []
        
        # Process each message in the thread
        for message in thread['messages']:
            # Get message details
            msg = service.users().messages().get(
                userId='me',
                id=message['id'],
                format='full'
            ).execute()
            
            # Extract headers
            headers = msg['payload']['headers']
            
            # Get sender info
            sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown')
            
            # Extract sender name and email
            if '<' in sender and '>' in sender:
                sender_name = sender.split('<')[0].strip()
                sender_email = sender.split('<')[1].split('>')[0].strip().lower()
            else:
                sender_email = sender.lower()
                sender_name = sender_email.split('@')[0] if '@' in sender_email else sender_email
            
            # Get recipients (To, Cc)
            recipients = []
            for header in headers:
                if header['name'].lower() in ['to', 'cc']:
                    recipients.extend([addr.strip() for addr in header['value'].split(',')])
            
            # Add sender and recipients to participants dict if not the account owner
            if sender_email.lower() != account_owner_email.lower():
                result['participants'][sender_email] = sender_name
            
            # Process recipients
            for recipient in recipients:
                if '<' in recipient and '>' in recipient:
                    recipient_name = recipient.split('<')[0].strip()
                    recipient_email = recipient.split('<')[1].split('>')[0].strip().lower()
                else:
                    recipient_email = recipient.lower()
                    recipient_name = recipient_email.split('@')[0] if '@' in recipient_email else recipient_email
                
                if recipient_email.lower() != account_owner_email.lower():
                    result['participants'][recipient_email] = recipient_name
            
            # Get message body
            body = ""
            
            # Function to extract text from message parts
            def get_text_from_part(part):
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        import base64
                        # Decode base64url encoded data
                        decoded_bytes = base64.urlsafe_b64decode(data.encode('ASCII'))
                        decoded_text = decoded_bytes.decode('utf-8')
                        return decoded_text
                    return ""
                
                if part.get('parts'):
                    text = ""
                    for subpart in part.get('parts'):
                        text += get_text_from_part(subpart)
                    return text
                
                return ""
            
            # Get message text
            if 'parts' in msg['payload']:
                body = get_text_from_part(msg['payload'])
            elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                import base64
                data = msg['payload']['body']['data']
                decoded_bytes = base64.urlsafe_b64decode(data.encode('ASCII'))
                body = decoded_bytes.decode('utf-8')
            
            # Clean up the message text
            # Remove common email signatures and reply indicators
            lines = body.split('\n')
            cleaned_lines = []
            
            skip_line = False
            for line in lines:
                # Skip common email markers including the > characters for quoted text
                if any(marker in line.lower() for marker in [
                    'from:', 'sent:', 'to:', 'cc:', 'subject:', 
                    'on ', 'wrote:', 'original message', '________________________________',
                    '-----original message-----', 'forwarded message', 
                    'begin forwarded message', '>', '>>', '>>>', '>>>>', '>>>>>', '>>>>>>', '>>>>>>>', '>>>>>>>>'
                ]):
                    skip_line = True
                    continue
                
                # Reset skip_line flag if we encounter a non-empty line after skipping
                if skip_line and line.strip():
                    skip_line = False
                
                if not skip_line and line.strip():
                    cleaned_lines.append(line.strip())
            
            # Join the cleaned lines
            cleaned_body = ' '.join(cleaned_lines)
            
            # Add sender name and cleaned message to the conversation
            if cleaned_body.strip():
                processed_conversation.append(f"{sender_name}: {cleaned_body}")
        
        # Join the processed messages in chronological order (oldest first)
        result['thread'] = '\n\n'.join(processed_conversation)
        
        return result
    
    except Exception as e:
        return {
            'participants': {},
            'thread': f"Error processing thread: {str(e)}"
        }
def start_mongodb(location="mongodb://localhost:27017"):
    '''
    Creates a mongodb client for the local db or Atlas based db.
    General structure of the db:
friends (db)
├── people (collection)
│   └── Document example:
│       {
│         "email": "person@example.com",
│         "name": "Jane Doe",
│         "primary_relationship": "client",
│         "tags": ["project", "feedback"],
│         "summary": "Talked about a new contract.",
│         "sentiment_average": 0.7,
│         "messages_to_person": 3,
│         "messages_from_person": 1,
│         "timestamp": "2025-04-10T12:00:00Z"
|         "threads_analized": 1 
│           }
│         ]
│       }

├── tags_master (collection)
│   └── Document example:
│       {
│         "type": "primary_relationship",
│         "tags": ["client", "manager", "friend", "vendor"]
│       }
│
│       {
│         "type": "secondary_tag",
│         "tags": ["project", "referral", "feedback", "support"]
│       } 
    '''
    mongo_client = MongoClient(location)
    friends_db = mongo_client["friends"]
    return friends_db
def get_genai_client(api_key):
    genai_client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1alpha")
        )
    return genai_client
def process_thread_with_genai_and_store(genai_client, thread_dic:dict, owner:dict, db): 
    # Can't accurately determine sentiment if so many people are involved in the thread
    if len(thread_dic['participants']) > 10:
        return
    prompt =  \
   f'''
You are an expert relationship and communication intelligence assistant.
Your task:
Analyze the provided email thread and generate a structured JSON output.
Input:
- Email thread (as a single string): {thread_dic['thread']}
- List of participants (name and email): {thread_dic['participants']}
- Account owner's name and email: {owner['name']} ({owner['email']})
Output format:
- Output **only** a raw JSON object.
- Do **not** use any markdown, code block markers (e.g., ```json), or extra text.
- Ensure the JSON can be parsed by `json.loads()` in Python without modification.
- Use **double quotes** for all keys and string values.
- If the thread appears to be a delivery failure, an automated message, or spam, **output the string "AVOID"** (no JSON object, just the raw string).
For each participant (excluding the owner), the JSON keys must be their email addresses.
Each participant should have an object with the following fields:
- "name": Their full name
- "primary_relationship": Brief label (e.g., "colleague", "manager", "client", etc.)
- "tags": 2–4 keywords summarizing relationship and context
- "summary": 1–2 sentence summary of the interaction between them and the owner
- "sentiment": A float sentiment score from -1.0 (very negative) to 1.0 (very positive)
- "messages_to_person": Number of messages the owner sent to this person
- "messages_from_person": Number of messages this person sent to the owner
Only output the JSON object or the string "AVOID". No extra commentary.
''' 
    response = genai_client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents=prompt
    )
    raw_output=response.text
    if raw_output.upper().strip() == "AVOID":
        print("Gemini flagged this thread as irrelevant — skipping.")
        return 
    cleaned = re.sub(r"^```json|^```|```|^```python", "", raw_output.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        response_json = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError) as err:
        print(f'{err}: Couldn\'t process genai output')
        print("Raw LLM output:\n",response.text)
        print("Cleaned LLM output:\n",cleaned)
        return 
    people_collection = db["people"]
    tags_collection = db["tags"]
    for email, person_data in response_json.items():
        db_person_instance = people_collection.find_one({"email":email})
        threads_analized = 0
        messages_to = person_data.get("messages_to_person", 0)
        messages_from= person_data.get("messages_from_person", 0) 
        new_summary = person_data.get("summary")
        new_primary_relationship = person_data.get("primary_relationship","")
        remove_old_relationship = False
        new_tags = person_data.get("tags",[])

        if db_person_instance:
            messages_from += db_person_instance.get("messages_from_person",0)
            messages_to += db_person_instance.get("messages_to_person",0)
            threads_analized = db_person_instance.get("threads_analized",0)
            old_sentiment_average = db_person_instance.get("sentiment_average", 0)
            new_sentiment_average = (old_sentiment_average * threads_analized+ person_data["sentiment"] )  /(threads_analized+1)
            old_summary = db_person_instance.get("summary","") 
            old_primary_relationship = db_person_instance.get("primary_relationship","")
            prompt_for_relationship_concat = \
            f'''
You are an AI trained in social and professional relationship intelligence.
You are given two relationship labels that describe how a person relates to the account owner. Choose the one that best reflects the primary relationship between them, based on clarity, role importance, and communication context.
### Relationships:
- Previous relationship: "{old_primary_relationship}"
- New relationship: "{new_primary_relationship}"
Choose the most appropriate one to use as the primary label going forward.
### Output format:
Return only the better relationship label as a **lowercase string** (e.g., "recruiter", "manager"). Do not include any explanation, markdown, or formatting.
            '''
            concat_relationship_response =  genai_client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents=prompt_for_relationship_concat
            )
            new_primary_relationship = concat_relationship_response.text.strip()
            if new_primary_relationship != old_primary_relationship:
                remove_old_relationship = True                

            prompt_for_summary_concat = \
            f'''
You are an AI assistant that refines and expands relationship summaries based on new information.

Here is the existing summary:
"{old_summary}"
Here is the new summary to integrate:
"{new_summary}"
Your task is to intelligently combine both summaries into a single, updated version. 
Keep it concise (2–3 sentences), clear, and non-redundant. 
Preserve important details from both inputs and ensure a consistent tone and style.
Output only the updated summary without any extra formatting or commentary. 
            '''
            concat_summary_response = genai_client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents=prompt_for_summary_concat
            )
            new_summary = concat_summary_response.text.strip()
            new_tags = list(set(new_tags + db_person_instance.get("tags",[])))
        else:
            new_sentiment_average = person_data.get("sentiment",0)

        threads_analized += 1 
        insert_instance = {
            "email": email,
            "name": person_data.get("name"),
            "primary_relationship": new_primary_relationship,
            "tags": new_tags,
            "summary": new_summary,
            "sentiment_average": new_sentiment_average,  
            "messages_to_person": messages_to,
            "messages_from_person": messages_from,
            "threads_analized": threads_analized 
        }
        
        people_collection.update_one(
            {"email": email},
            {"$set":insert_instance},
            upsert=True 
        )
        

        ### Update relationships and tags too
        primary_rel = person_data.get("primary_relationship")
        if primary_rel:
            db_relationship_instance = tags_collection.find_one({"type": "primary_relationship"})
            current_relationships = set(db_relationship_instance.get("tags", [])) if db_relationship_instance else set()
            updated_relationships = sorted(current_relationships | {primary_rel})
            if remove_old_relationship:
                updated_relationships.discard(old_primary_relationship)

            tags_collection.update_one(
                {"type": "primary_relationship"},
                {"$set": {"tags": updated_relationships}},
                upsert=True
            )

        ###  Update secondary_tags list
        new_tags_list = person_data.get("tags", [])
        if new_tags_list:
            db_tags_instance = tags_collection.find_one({"type": "secondary_tag"})
            current_tags = set(db_tags_instance.get("tags", [])) if db_tags_instance else set()
            updated_tags = sorted(current_tags | set(new_tags_list))

            tags_collection.update_one(
                {"type": "secondary_tag"},
                {"$set": {"tags": updated_tags}},
                upsert=True
            )
def process_thread_wrapper(thread_id_owner_creds):
    thread_id, owner,creds = thread_id_owner_creds
    # re-create clients inside subprocess
    gmail_service = build("gmail", "v1", credentials=creds)
    thread_dic = process_gmail_thread(gmail_service,thread_id,owner['email'])
    db = start_mongodb()
    genai_client = get_genai_client(API_KEY)

    return process_thread_with_genai_and_store(genai_client, thread_dic, owner, db)
      


def main(): 
    
    
    #### GOOGLE SDK SET UP 

    creds = authorize_account()
    if not creds:
        print("Could not authorize account")
        sys.exit(1)
    gmail_service = build("gmail", "v1", credentials=creds)
    people_service = build("people", "v1", credentials=creds) 
    owner = get_owner_dic(gmail_service,people_service)
    thread_ids = get_sent_messages_threads(gmail_service)
    ############

    #### PROCESS EMAILS IN MUTITHREADS
    tasks = [(thread_id, owner, creds) for thread_id in thread_ids]
    with ProcessPoolExecutor(os.cpu_count()) as executor:
        executor.map(process_thread_wrapper, tasks)
    #######

    ################## DEBUG
    #### Testing Gemini
    # thread_id_for_testing = '1808575587600d97'
    # dbs_client = start_mongodb()
    # genai_client = get_genai_client(API_KEY)
    # test_thread_processed = process_gmail_thread(service,thread_id_for_testing, owner_email) 
    # process_thread_with_genai_and_store(genai_client,test_thread_processed,owner,dbs_client)
    ###################


    ## Testing processing_gmail_threads
    # count = 0
    # for thread_id in thread_ids:
    #     count+=1
    #     pprint(process_gmail_thread(service,thread_id, owner_email))
    #     # print(parse_thread(thread_id,service,owner_email)["thread_text"])
    #     if count==1:
    #         break
    ########
 
if __name__ == "__main__":
    main()
