import streamlit as st
import boto3
import json
import os

# CSS for the chat interface and responses
st.markdown('''
<style>
.chat-message {padding: 1.5rem; border-radius: 0.5rem; margin-bottom: 1rem; display: flex}
.chat-message.user {background-color: #2b313e}
.chat-message.bot {background-color: #475063}
.chat-message .avatar {width: 20%}
.chat-message .avatar img {max-width: 78px; max-height: 78px; border-radius: 50%; object-fit: cover}
.chat-message .message {width: 80%; padding: 0 1.5rem; color: #fff}
.response, .url {background-color: #f0f0f0; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;}
</style>
''', unsafe_allow_html=True)

# Message templates
bot_template = '''
<div class="chat-message bot">
    <div class="avatar">
        <img src="https://i.ibb.co/cN0nmSj/Screenshot-2023-05-28-at-02-37-21.png">
    </div>
    <div class="message">{{MSG}}</div>
</div>
'''

user_template = '''
<div class="chat-message user">
    <div class="avatar">
        <img src="https://i.ibb.co/wRtZstJ/Aurora.png">
    </div>    
    <div class="message">{{MSG}}</div>
</div>
'''

secret_name = "opensearch_serverless_secrets"

st.title("Chat with Bedrock Knowledge Base to Test Semantic Chunking")

session = boto3.session.Session()
region_name = session.region_name
bedrock_client = boto3.client('bedrock-agent-runtime')

client = session.client(
    service_name='secretsmanager',
    region_name=region_name
)

get_secret_value_response = client.get_secret_value(
    SecretId=secret_name
)

secret = get_secret_value_response['SecretString']
parsed_secret = json.loads(secret)

knowledge_base_id = parsed_secret["KNOWLEDGE_BASE_ID"]

# Initialize conversation history if not present
if 'conversation_history' not in st.session_state:
    st.session_state.conversation_history = []

user_input = st.text_input("You: ")

if st.button("Send"):
    # Retrieve and Generate call
    response = bedrock_client.retrieve_and_generate(
        input={"text": user_input},
        retrieveAndGenerateConfiguration={
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": knowledge_base_id,
                "modelArn": f"arn:aws:bedrock:{region_name}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
            },
            "type": "KNOWLEDGE_BASE"
        }
    )
    print(response)
    # Extract response
    response_text = response['output']['text']

    # Check if there are any retrieved references
    if not response['citations'][0]['retrievedReferences']:
        # No references found, use the response text
        display_text = response_text
    else:
        # Handle normal case with references
        # Extract S3 URI (assuming references are present)
        s3_uri = response['citations'][0]['retrievedReferences'][0]['location']['s3Location']['uri']
        display_text = f"{response_text}<br><br>Reference: {s3_uri}"

    # Insert the response at the beginning of the conversation history
    st.session_state.conversation_history.insert(0, ("Assistant", f"<div class='response'>{display_text}</div>"))
    st.session_state.conversation_history.insert(0, ("You", user_input))

    # Display conversation history
    for speaker, text in st.session_state.conversation_history:
        if speaker == "You":
            st.markdown(user_template.replace("{{MSG}}", text), unsafe_allow_html=True)
        else:
            st.markdown(text, unsafe_allow_html=True)
    