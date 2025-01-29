import gradio as gr
import requests
import json
import os
import re

MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "http://localhost:8080")

# Get credentials from environment variables
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")

def authenticate(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def query_model(question):
    url = f"{MODEL_BASE_URL}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        content = result['choices'][0]['message']['content']
        # Remove <think> and </think> tags
        content = re.sub(r'<think>|</think>', '', content).strip()
        return content
    else:
        return f"Error: {response.status_code} - {response.text}"

def chatbot(message, history):
    response = query_model(message)
    history.append((message, response))
    return history

def create_demo():
    with gr.Blocks() as demo:
        gr.Markdown("# DeepSeek AI Chatbot")
        
        with gr.Tab("Login"):
            username = gr.Textbox(label="Username")
            password = gr.Textbox(label="Password", type="password")
            login_button = gr.Button("Login")
            login_message = gr.Markdown(visible=False)

        with gr.Tab("Chatbot", visible=False) as chatbot_tab:
            chatbot = gr.Chatbot(height=300)
            msg = gr.Textbox(placeholder="Type your message here...", label="User Input")
            clear = gr.Button("Clear")

            def user(user_message, history):
                return "", history + [[user_message, None]]

            def bot(history):
                user_message = history[-1][0]
                bot_message = query_model(user_message)
                history[-1][1] = bot_message
                return history

            msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
                bot, chatbot, chatbot
            )
            clear.click(lambda: None, None, chatbot, queue=False)

        def login(username, password):
            if authenticate(username, password):
                return (
                    gr.update(value="Login successful!", visible=True),  # login_message
                    gr.update(visible=True),  # chatbot_tab
                    "",  # username
                    "",  # password
                )
            else:
                return (
                    gr.update(value="Invalid credentials. Please try again.", visible=True),  # login_message
                    gr.update(visible=False),  # chatbot_tab
                    gr.update(),  # username (no change)
                    gr.update(),  # password (no change)
                )

        login_button.click(login, inputs=[username, password], outputs=[login_message, chatbot_tab, username, password])

    return demo

if __name__ == "__main__":
    demo = create_demo()
    demo.launch(server_name="0.0.0.0", server_port=7860)