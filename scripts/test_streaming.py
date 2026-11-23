import os
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key=os.environ["GATEWAY_API_KEY"])

for model in ["llama3.2", "groq-gpt-oss", "gemini-flash"]:
    print(f"\n[{model}] ", end="", flush=True)

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Write a 4-line poem about Docker."}],
        stream=True,
        stream_options={"include_usage": True},
    )

    # Print each piece of text as soon as it arrives
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
        if chunk.usage:
            print(f"\n  tokens: {chunk.usage.prompt_tokens} in / {chunk.usage.completion_tokens} out")
