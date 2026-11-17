from openai import OpenAI

# Point the official SDK at your gateway instead of OpenAI's servers
client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed-yet")

resp = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "system", "content": "Answer in one short sentence."},
        {"role": "user", "content": "What is an LLM gateway?"},
    ],
)

print("Answer:", resp.choices[0].message.content)
print("Usage: ", resp.usage)