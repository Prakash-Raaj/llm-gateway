import os
from openai import OpenAI

# Point the official SDK at your gateway instead of OpenAI's servers
client = OpenAI(base_url="http://localhost:8000/v1", api_key=os.environ["GATEWAY_API_KEY"])

# Same request, only the model name changes -> different provider
for model in ["llama3.2", "groq-gpt-oss", "gemini-flash"]:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Answer in one short sentence."},
            {"role": "user", "content": "What is an LLM gateway?"},
        ],
    )
    print(f"\n[{model}] {resp.choices[0].message.content}")
    print(f"  tokens: {resp.usage.prompt_tokens} in / {resp.usage.completion_tokens} out")

    # bearer token to test gw_JWVPf62pooJyOMxBphgacqcAHAY3CIAh-AuyV34SXmE
