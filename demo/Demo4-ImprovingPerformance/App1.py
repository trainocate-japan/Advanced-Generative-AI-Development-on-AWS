import streamlit as st
import boto3
import json
import os
import time
from datetime import datetime
import traceback

# Cost per token rates
COST_RATES = {
    "Claude Instant": {
        "input": 0.0000008,
        "output": 0.0000008
    },
    "Claude 3 Haiku": {
        "input": 0.00000025,
        "output": 0.00000025
    }
}

# Updated CSS with consistent styling
st.markdown('''
<style>
/* Base styles */
.chat-message {
    padding: 1.5rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    display: flex;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

.chat-message.user {
    background-color: #000000;
}

.chat-message.bot {
    background-color: #000000;
}

.chat-message .avatar {
    width: 20%;
}

.chat-message .avatar img {
    max-width: 78px;
    max-height: 78px;
    border-radius: 50%;
    object-fit: cover;
}

.chat-message .message {
    width: 80%;
    padding: 0 1.5rem;
    color: #fff;
    font-size: 1rem;
    line-height: 1.5;
}

/* Consistent response styling */
.response-container {
    background-color: #ffffff;
    border-radius: 0.5rem;
    margin: 1rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.response-content {
    background-color: #ffffff;
    color: #1a1a1a;
    padding: 1.5rem;
    border-radius: 0.5rem;
    font-size: 1rem;
    line-height: 1.6;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Metrics styling */
.metrics-box {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    border: 1px solid #dee2e6;
}

.token-metrics {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0.5rem 0.5rem 0 0;
    border-bottom: 1px solid #dee2e6;
    color: #1a1a1a;
    font-size: 0.9rem;
}

.cost-metrics {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0 0 0.5rem 0.5rem;
    color: #1a1a1a;
    font-size: 0.9rem;
    border-left: 4px solid #28a745;
}

.metric-header {
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 0.5rem;
    font-size: 0.95rem;
}

.metric-value {
    color: #1a1a1a;
    margin-left: 1rem;
    font-size: 0.9rem;
}
</style>
''', unsafe_allow_html=True)

# Message templates with consistent styling
bot_template = '''
<div class="chat-message bot">
    <div class="avatar">
        <img src="https://i.ibb.co/cN0nmSj/Screenshot-2023-05-28-at-02-37-21.png">
    </div>
    <div class="message">
        <div class="response-container">{{MSG}}</div>
    </div>
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

st.title("Chat with Bedrock Knowledge Base and compare Models")

# Initialize session state variables
if 'response_times' not in st.session_state:
    st.session_state.response_times = []
    st.session_state.timestamps = []
    st.session_state.input_tokens = []
    st.session_state.output_tokens = []
    st.session_state.total_tokens = []
    st.session_state.request_costs = []
    st.session_state.total_cost = 0.0

def calculate_cost(input_tokens, output_tokens, model):
    """
    Calculate cost based on token usage and model rates
    """
    rates = COST_RATES[model]
    input_cost = input_tokens * rates["input"]
    output_cost = output_tokens * rates["output"]
    return input_cost + output_cost

# Create four columns for metrics
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

with col1:
    if st.session_state.response_times:
        st.metric("Latest Response Time", f"{st.session_state.response_times[-1]:.2f}s")
        st.metric("Average Response Time", f"{sum(st.session_state.response_times)/len(st.session_state.response_times):.2f}s")

with col2:
    if st.session_state.input_tokens:
        st.metric("Input Tokens", st.session_state.input_tokens[-1])
        st.metric("Output Tokens", st.session_state.output_tokens[-1])
        st.metric("Total Tokens", st.session_state.total_tokens[-1])

with col3:
    if st.session_state.request_costs:
        st.metric("Latest Request Cost", f"${st.session_state.request_costs[-1]:.6f}")
        st.metric("Total Cost", f"${st.session_state.total_cost:.6f}")

with col4:
    if st.session_state.response_times:
        st.subheader("Response Time")
        chart_data = {
            'Time': st.session_state.timestamps,
            'Response Time (s)': st.session_state.response_times
        }
        st.line_chart(chart_data, x='Time', y='Response Time (s)')

# Setup AWS clients
try:
    session = boto3.session.Session()
    region_name = session.region_name
    bedrock_runtime_client = boto3.client('bedrock-runtime')
    bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')
    secrets_client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    # Get secrets
    secret_name = "opensearch_serverless_secrets"
    get_secret_value_response = secrets_client.get_secret_value(
        SecretId=secret_name
    )
    secret = get_secret_value_response['SecretString']
    parsed_secret = json.loads(secret)
    knowledge_base_id = parsed_secret["KNOWLEDGE_BASE_ID"]
except Exception as e:
    st.error(f"Error setting up AWS clients: {str(e)}")
    st.stop()

# Model selection
model_options = {
    "Claude Instant": "anthropic.claude-instant-v1",
    "Claude 3 Haiku": "anthropic.claude-3-haiku-20240307-v1:0"
}

selected_model = st.selectbox("Select a model", list(model_options.keys()))

# Initialize conversation history if not present
if 'conversation_history' not in st.session_state:
    st.session_state.conversation_history = []

# Create a container for the chat interface
chat_container = st.container()

# Input section
user_input = st.text_input("You: ")
send_button = st.button("Send", key="send_button")

if send_button and user_input:
    success = False
    start_time = time.time()
    
    try:
        # Retrieve search results first
        retrieve_response = bedrock_agent_runtime_client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={'text': user_input}
        )
        
        # Format search results
        search_results = "\n".join([
            f"{i+1}. {ref['content']['text']}" 
            for i, ref in enumerate(retrieve_response.get('retrievalResults', [])[:5])
        ])
        
        # Construct messages in the correct format
        converse_response = bedrock_runtime_client.converse(
            modelId=model_options[selected_model],
            messages=[
                {
                    'role': 'user', 
                    'content': [{'text': f"""You are a question answering agent. Answer the user's question using only information from the provided search results. Do not add any additional note in the begining except the search results.

Search Results:
{search_results}

Question: {user_input}"""}]
                }
            ],
            inferenceConfig={'maxTokens': 2048}
        )
        
        success = True
        
        if success:
            # Calculate response time
            response_time = time.time() - start_time
            st.session_state.response_times.append(response_time)
            st.session_state.timestamps.append(datetime.now().strftime('%H:%M:%S'))
            
            # Extract response text and token usage from the response
            response_text = converse_response['output']['message']['content'][0]['text']
            input_tokens = converse_response['usage']['inputTokens']
            output_tokens = converse_response['usage']['outputTokens']
            total_tokens = input_tokens + output_tokens
            
            # Calculate cost
            request_cost = calculate_cost(input_tokens, output_tokens, selected_model)
            st.session_state.total_cost += request_cost
            
            # Store metrics
            st.session_state.input_tokens.append(input_tokens)
            st.session_state.output_tokens.append(output_tokens)
            st.session_state.total_tokens.append(total_tokens)
            st.session_state.request_costs.append(request_cost)
            
            # Updated response formatting with consistent styling
            token_metrics = f"""<div class='token-metrics'>
                <div class='metric-header'>Token Usage</div>
                <div class='metric-value'>
                    Input Tokens: {input_tokens:,}<br>
                    Output Tokens: {output_tokens:,}<br>
                    Total Tokens: {total_tokens:,}
                </div>
            </div>"""
            
            cost_metrics = f"""<div class='cost-metrics'>
                <div class='metric-header'>Cost Breakdown</div>
                <div class='metric-value'>
                    Input Cost: ${(input_tokens * COST_RATES[selected_model]["input"]):.6f}<br>
                    Output Cost: ${(output_tokens * COST_RATES[selected_model]["output"]):.6f}<br>
                    Total Request Cost: ${request_cost:.6f}<br>
                    Cumulative Session Cost: ${st.session_state.total_cost:.6f}
                </div>
            </div>"""
            
            display_text = f"""
            <div class='metrics-box'>
                {token_metrics}
                {cost_metrics}
            </div>
            <div class='response-content'>{response_text}</div>
            """
            
            # Update conversation history
            st.session_state.conversation_history.insert(0, ("Assistant", display_text))
            st.session_state.conversation_history.insert(0, ("You", user_input))
            
            # Rerun to update metrics and graph
            st.rerun()
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.error(f"Full traceback: {traceback.format_exc()}")
        error_message = f"<div class='response-content'>An error occurred: {str(e)}</div>"
        st.session_state.conversation_history.insert(0, ("Assistant", error_message))
        st.session_state.conversation_history.insert(0, ("You", user_input))

# Display conversation history
with chat_container:
    for speaker, text in st.session_state.conversation_history:
        if speaker == "You":
            st.markdown(user_template.replace("{{MSG}}", text), unsafe_allow_html=True)
        else:
            st.markdown(bot_template.replace("{{MSG}}", text), unsafe_allow_html=True)        