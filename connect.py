from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8010/v1",
    api_key="local-secret",
)

response = client.responses.create(
    model="gpt-5.4",
    input="Explain retrieval-augmented generation.",
)

print(response.output_text)

