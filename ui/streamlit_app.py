
import streamlit as st
import requests
import os
# FastAPI backend URL
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/ask")

# Page configuration
st.set_page_config(
    page_title="IT Support Copilot",
    page_icon="🤖",
    layout="centered"
)

# Application title
# Custom styling
st.markdown("""
<style>
.main-title {
    text-align: center;
    font-size: 48px;
    font-weight: 800;
    margin-bottom: 10px;
}

.subtitle {
    text-align: center;
    color: gray;
    font-size: 18px;
    margin-bottom: 35px;
}
</style>
""", unsafe_allow_html=True)

# Centered heading
st.markdown(
    '<h1 class="main-title">🤖 IT Support Copilot</h1>',
    unsafe_allow_html=True
)

st.markdown(
    '<p class="subtitle">AI-powered Enterprise IT Support Assistant</p>',
    unsafe_allow_html=True
)

# Store chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("sources"):
            with st.expander("View Sources"):
                for source in message["sources"]:
                    if source.get("url"):
                        st.markdown(
                            f"- [{source.get('title', 'Source')}]"
                            f"({source['url']})"
                        )
                    elif source.get("document"):
                        st.write(
                            f"- {source['document']} "
                            f"(Section: {source.get('section', 'N/A')})"
                        )

        if message.get("status"):
            st.caption(f"Status: {message['status']}")

# Chat input
question = st.chat_input("Ask your IT support question...")

if question:

    # Display employee question
    st.session_state.messages.append({
        "role": "user",
        "content": question
    })

    with st.chat_message("user"):
        st.markdown(question)

    # Generate AI response
    with st.chat_message("assistant"):

        with st.spinner("AI agent is processing your question..."):

            try:
                response = requests.post(
                    API_URL,
                    json={"question": question},
                    timeout=120
                )

                response.raise_for_status()

                result = response.json()

                answer = result["answer"]
                sources = result.get("sources", [])
                status = result.get("status", "unknown")

            except requests.exceptions.RequestException as error:

                answer = (
                    "Unable to connect to the IT Support backend. "
                    "Please check whether FastAPI is running."
                )

                sources = []
                status = "error"

                st.error(str(error))

        # Display answer
        st.markdown(answer)

        # Display sources
        if sources:
            with st.expander("View Sources"):
                for source in sources:

                    if source.get("url"):
                        st.markdown(
                            f"- [{source.get('title', 'Source')}]"
                            f"({source['url']})"
                        )

                    elif source.get("document"):
                        st.write(
                            f"- {source['document']} "
                            f"(Section: {source.get('section', 'N/A')})"
                        )

        st.caption(f"Status: {status}")

        # Save assistant response
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "status": status
        })

